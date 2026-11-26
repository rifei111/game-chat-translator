"""语音转文字：soundcard 采集（麦克风 / 系统回环）+ faster-whisper 本地转写。

采集与转写分线程，转写时不会丢音频；每段默认 5 秒，VAD 过滤空白。
"""
from __future__ import annotations

import collections
import logging
import os
import queue
import threading
import time
from typing import Callable

log = logging.getLogger("asr")

SAMPLE_RATE = 16000
BLOCK = 1600  # 100 ms

# 常见的 Whisper 静默幻觉，直接丢弃
_HALLUCINATION = (
    "thank you for watching",
    "subscribe",
    "字幕由",
    "请不吝点赞",
    "amara.org",
    "www.youtube.com",
)


def _norm(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum())


class AsrEngine:
    def __init__(self, model_dir: str,
                 on_text: Callable[[str, str, float], None],
                 on_status: Callable[[str, str], None],
                 on_log: Callable[[str, str], None]):
        self.model_dir = model_dir
        self.on_text = on_text
        self.on_status = on_status
        self.on_log = on_log

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._model = None
        self._model_name = ""
        self._status = "idle"
        self._status_detail = ""
        self._error = ""
        self._device_id = ""
        self._device_name = ""
        self._language = ""
        self._levels: collections.deque[float] = collections.deque(maxlen=56)
        self._rms = 0.0
        self._last_text = ""
        self._last_text_at = 0.0
        self._preparing = False

    # ---- 查询 ----
    def devices(self) -> dict:
        try:
            import soundcard as sc
            speakers = sc.all_speakers()
            spk_names = {s.name for s in speakers}
            items = []
            for m in sc.all_microphones(include_loopback=True):
                is_loop = m.name in spk_names or "CABLE Input" in m.name
                items.append({
                    "id": m.id,
                    "name": m.name,
                    "kind": "loopback" if is_loop else "microphone",
                    "label": ("系统声音 · " if is_loop else "麦克风 · ") + m.name,
                })
            # 回环设备排前面
            items.sort(key=lambda x: (0 if x["kind"] == "loopback" else 1, x["name"]))
            default = next((x["id"] for x in items if x["kind"] == "loopback"), "")
            return {"ok": True, "devices": items, "default": default}
        except Exception as e:
            log.warning("枚举音频设备失败：%s", e)
            return {"ok": False, "devices": [], "default": "", "error": str(e)}

    def model_state(self, model: str) -> dict:
        folder = os.path.join(
            self.model_dir, f"models--Systran--faster-whisper-{model}"
        )
        total = 0
        found = False
        if os.path.isdir(folder):
            for root, _, files in os.walk(folder):
                for name in files:
                    if name == "model.bin":
                        found = True
                    try:
                        total += os.path.getsize(os.path.join(root, name))
                    except OSError:
                        pass
        return {
            "model": model,
            "downloaded": found,
            "size_mb": round(total / (1024 * 1024), 1),
            "folder": folder,
        }

    def levels(self) -> dict:
        with self._lock:
            return {
                "levels": list(self._levels),
                "rms": round(self._rms, 3),
                "status": self._status,
                "detail": self._status_detail,
                "error": self._error,
                "device": self._device_name,
                "model": self._model_name or "",
                "language": self._language,
            }

    def status(self) -> dict:
        with self._lock:
            return {
                "status": self._status,
                "detail": self._status_detail,
                "error": self._error,
                "running": bool(self._thread and self._thread.is_alive()),
                "device": self._device_name,
                "model": self._model_name,
                "language": self._language,
            }

    def _set_status(self, status: str, detail: str = ""):
        with self._lock:
            self._status = status
            self._status_detail = detail
        self.on_status(status, detail)

    # ---- 模型 ----
    def _load_model(self, model: str):
        if self._model is not None and self._model_name == model:
            return self._model
        os.makedirs(self.model_dir, exist_ok=True)
        info = self.model_state(model)
        if not info["downloaded"]:
            self.on_log(f"首次使用 {model} 模型，正在下载（约 145 MB，需联网一次）", "info")
        else:
            self.on_log(f"加载本地语音模型 {model}（{info['size_mb']} MB）", "info")
        from faster_whisper import WhisperModel
        t0 = time.time()
        self._model = WhisperModel(
            model, device="cpu", compute_type="int8",
            download_root=self.model_dir,
            cpu_threads=max(2, min(8, os.cpu_count() or 4)),
        )
        self._model_name = model
        self.on_log(f"语音模型就绪，用时 {time.time() - t0:.1f}s", "ok")

    def prepare(self, model: str):
        if self._preparing or self._status in ("listening", "transcribing"):
            return {"ok": True, "preparing": True}
        self._preparing = True
        self._set_status("preparing", "正在准备语音模型")

        def _work():
            try:
                self._load_model(model)
                if self._status == "preparing":
                    self._set_status("ready", "语音模型已就绪")
            except Exception as e:
                self._error = str(e)
                self.on_log(f"语音模型准备失败：{e}", "error")
                self._set_status("error", str(e))
            finally:
                self._preparing = False

        threading.Thread(target=_work, daemon=True, name="asr-prepare").start()
        return {"ok": True, "preparing": True}

    # ---- 启停 ----
    def start(self, model: str, device_id: str, language: str = "",
              chunk: float = 5.0):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {"ok": False, "error": "语音识别已在运行"}
            self._stop.clear()
            self._error = ""
            self._language = language
            self._device_id = device_id
            self._last_text = ""
            self._levels.clear()
            self._rms = 0.0
            self._thread = threading.Thread(
                target=self._run, args=(model, device_id, language, float(chunk)),
                daemon=True, name="asr-worker",
            )
            self._thread.start()
        return {"ok": True}

    def stop(self):
        self._stop.set()
        self._set_status("stopping", "正在停止语音识别")
        thread = self._thread
        if thread:
            thread.join(timeout=4.0)
        self._thread = None
        self._set_status("idle", "已停止")
        return {"ok": True}

    def _resolve_device(self, device_id: str):
        import soundcard as sc
        if device_id:
            try:
                mic = sc.get_microphone(device_id, include_loopback=True)
                return mic
            except Exception:
                pass
        # 默认：第一个回环，其次第一个麦克风
        speakers = {s.name for s in sc.all_speakers()}
        mics = sc.all_microphones(include_loopback=True)
        for mic in mics:
            if mic.name in speakers:
                return mic
        return mics[0] if mics else None

    def _run(self, model: str, device_id: str, language: str, chunk: float):
        try:
            self._set_status("preparing", "加载语音模型")
            self._load_model(model)
            mic = self._resolve_device(device_id)
            if mic is None:
                raise RuntimeError("没有找到可用的音频输入设备")
            self._device_name = mic.name
            self._set_status("listening", f"正在聆听：{mic.name}")
            self.on_log(f"语音识别已启动：{mic.name} · {model}", "ok")

            audio_q: queue.Queue = queue.Queue(maxsize=6)
            stop = self._stop
            chunk_samples = int(SAMPLE_RATE * max(2.0, chunk))

            def capture():
                try:
                    import numpy as np
                    with mic.recorder(samplerate=SAMPLE_RATE, channels=1,
                                      blocksize=BLOCK) as rec:
                        buf = []
                        total = 0
                        while not stop.is_set():
                            data = rec.record(numframes=BLOCK)
                            if data is None or len(data) == 0:
                                continue
                            mono = data[:, 0] if getattr(data, "ndim", 1) > 1 else data
                            mono = np.asarray(mono, dtype=np.float32)
                            rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
                            with self._lock:
                                self._rms = min(1.0, rms * 14)
                                self._levels.append(min(1.0, rms * 14))
                            buf.append(mono.copy())
                            total += len(mono)
                            if total >= chunk_samples:
                                audio = np.concatenate(buf)
                                peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
                                if peak > 0.0015:
                                    try:
                                        audio_q.put_nowait(audio)
                                    except queue.Full:
                                        pass
                                buf = []
                                total = 0
                except Exception as e:
                    self._error = str(e)
                    self.on_log(f"音频采集失败：{e}", "error")
                    self._set_status("error", str(e))
                    stop.set()
                finally:
                    try:
                        audio_q.put_nowait(None)
                    except Exception:
                        pass

            def transcribe():
                import numpy as np  # noqa: F401
                while not stop.is_set():
                    try:
                        audio = audio_q.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if audio is None:
                        break
                    self._set_status("transcribing", "识别中…")
                    try:
                        segments, info = self._model.transcribe(
                            audio,
                            language=language or None,
                            beam_size=1,
                            vad_filter=True,
                            vad_parameters={"min_silence_duration_ms": 350},
                            condition_on_previous_text=False,
                            no_speech_threshold=0.65,
                            temperature=0.0,
                        )
                        text = "".join(seg.text for seg in segments).strip()
                        text = " ".join(text.split())
                        if text and not any(h in text.lower() for h in _HALLUCINATION):
                            key = _norm(text)
                            now = time.time()
                            if key and not (key == _norm(self._last_text) and now - self._last_text_at < 6):
                                self._last_text = text
                                self._last_text_at = now
                                lang = (info.language or language or "unknown").lower()
                                prob = float(getattr(info, "language_probability", 1.0) or 1.0)
                                self.on_log(f"语音转写 [{lang}] {text}", "asr")
                                self.on_text(text, lang, prob)
                    except Exception as e:
                        self.on_log(f"语音转写失败：{e}", "error")
                        self._error = str(e)
                    finally:
                        if not stop.is_set():
                            self._set_status("listening", f"正在聆听：{mic.name}")

            cap = threading.Thread(target=capture, daemon=True, name="asr-capture")
            tr = threading.Thread(target=transcribe, daemon=True, name="asr-transcribe")
            cap.start()
            tr.start()
            cap.join()
            stop.set()
            tr.join(timeout=2.0)
        except Exception as e:
            self._error = str(e)
            log.exception("ASR failed")
            self.on_log(f"语音识别启动失败：{e}", "error")
            self._set_status("error", str(e))
        finally:
            with self._lock:
                self._thread = None
                if self._status not in ("error", "idle"):
                    self._status = "idle"
                    self._status_detail = "已停止"
