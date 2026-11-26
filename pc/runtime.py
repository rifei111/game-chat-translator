"""运行时：统一管理中继、手机服务、OCR 流水线、字幕条与语音识别。"""
from __future__ import annotations

import asyncio
import copy
import logging
import socket
import threading
import time
from collections import deque

from pc.asr import AsrEngine
from pc.config import Config, get_lan_ip
from pc.overlay import try_start_overlay
from pc.paths import config_path, data_dir, model_dir
from pc.phone_server import PhoneServer
from pc.pipeline import Pipeline
from pc.qr import qr_data_url
from pc.translator import build_translator
from relay.server import serve as relay_serve

log = logging.getLogger("runtime")


def free_port(start: int, tries: int = 20) -> int:
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", p))
                return p
            except OSError:
                continue
    return start


class Runtime:
    def __init__(self):
        self.cfg_path = config_path()
        self.cfg = Config.load(self.cfg_path)
        self.cfg.ensure_pair()
        self.cfg.save(self.cfg_path)

        self.lock = threading.RLock()
        self.pipeline: Pipeline | None = None
        self.overlay = None
        self.phone: PhoneServer | None = None
        self.engine_thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.ready = threading.Event()

        self.running = False
        self.starting = False
        self.status = "idle"
        self.status_text = "等待开始"
        self.started_at = 0.0
        self.last_error = ""
        self.peers = 0
        self._stop_requested = False
        self._voice_only = False
        self._sub_seq = 0
        self._log_seq = 0
        self.subs: deque[dict] = deque(maxlen=320)
        self.logs: deque[dict] = deque(maxlen=600)
        self.stats = {"ocr_lines": 0, "pushed": 0, "skipped": 0, "asr_segments": 0}

        self.asr = AsrEngine(
            model_dir(),
            on_text=self._on_asr_text,
            on_status=self._on_asr_status,
            on_log=self.log,
        )

        self.log("Lingua Studio 已就绪", "ok")
        self.log(f"数据目录：{data_dir()}", "info")

    # ---------------- 日志 / 事件 ----------------
    def log(self, msg: str, level: str = "info"):
        with self.lock:
            self._log_seq += 1
            item = {
                "id": self._log_seq,
                "ts": int(time.time() * 1000),
                "level": level,
                "msg": str(msg),
            }
            self.logs.append(item)
        if level in ("error", "warn"):
            log.warning(msg)
        else:
            log.info(msg)

    def _on_stats(self, stats: dict):
        with self.lock:
            self.stats = dict(stats)

    def _on_subtitle(self, msg: dict):
        with self.lock:
            self._sub_seq += 1
            msg = dict(msg)
            msg["id"] = self._sub_seq
            self.subs.append(msg)

    def _on_peers(self, peers: int):
        with self.lock:
            self.peers = int(peers)

    def _on_asr_text(self, text: str, lang: str, prob: float):
        with self.lock:
            pipe = self.pipeline
            running = self.running
        if not pipe or not running:
            self.log("语音识别已产生文本，但翻译流水线未启动", "warn")
            return
        pipe.submit(text, "asr", lang, prob, translate=self.cfg.asr_translate)

    def _on_asr_status(self, status: str, detail: str):
        mapping = {
            "preparing": "正在准备语音模型",
            "ready": "语音模型已就绪",
            "listening": detail or "正在聆听",
            "transcribing": "正在转写…",
            "stopping": "正在停止…",
            "idle": "语音识别已停止",
            "error": f"语音识别错误：{detail}",
        }
        text = mapping.get(status, detail or status)
        if status == "error":
            self.log(text, "error")
        elif status in ("listening", "ready"):
            self.log(text, "ok")

    # ---------------- 状态 ----------------
    def state(self) -> dict:
        with self.lock:
            pipe = self.pipeline
            relay_online = bool(pipe and pipe.relay.connected)
            asr_state = self.asr.status()
            return {
                "running": self.running,
                "starting": self.starting,
                "status": self.status,
                "status_text": self.status_text,
                "uptime": int(time.time() - self.started_at) if self.started_at else 0,
                "stats": dict(self.stats),
                "peers": self.peers,
                "relay_online": relay_online,
                "last_error": self.last_error,
                "asr": asr_state,
                "overlay": bool(self.overlay),
                "voice_only": bool(self._voice_only),
                "phone_url": self.cfg.phone_url,
                "relay_url": self.cfg.relay_url,
                "pair": self.cfg.pair,
                "ip": get_lan_ip(),
            }

    def get_delta(self, since_sub: int, since_log: int) -> dict:
        with self.lock:
            subs = [s for s in self.subs if s["id"] > since_sub][-80:]
            logs = [x for x in self.logs if x["id"] > since_log][-120:]
            return {
                "state": self.state(),
                "subtitles": subs,
                "logs": logs,
                "sub_cursor": subs[-1]["id"] if subs else since_sub,
                "log_cursor": logs[-1]["id"] if logs else since_log,
            }

    # ---------------- 启动 / 停止 ----------------
    def start(self, voice_only: bool = False) -> dict:
        with self.lock:
            if self.running or self.starting:
                return {"ok": False, "error": "已经在运行或正在启动"}
            self.starting = True
            self.status = "starting"
            self.status_text = "正在启动…"
            self._stop_requested = False
            self._voice_only = bool(voice_only)
            self.ready.clear()
            self.last_error = ""
        self.log("开始启动语音模式…" if voice_only else "开始启动翻译服务…", "info")
        threading.Thread(target=self._start_thread, daemon=True, name="start-engine").start()
        return {"ok": True, "starting": True}

    def _start_thread(self):
        try:
            with self.lock:
                cfg = self.cfg
            cfg.relay_port = free_port(cfg.relay_port)
            cfg.phone_port = free_port(cfg.phone_port)
            cfg.ensure_pair()
            cfg.save(self.cfg_path)

            phone = PhoneServer(cfg.phone_port)
            phone.start()
            with self.lock:
                self.phone = phone

            self.log(f"手机端地址：{cfg.phone_url}", "info")
            self.log(f"中继地址：{cfg.relay_url} · 配对码 {cfg.pair}", "info")

            overlay = try_start_overlay(cfg)
            with self.lock:
                self.overlay = overlay
                if overlay:
                    self.log("PC 字幕条已就绪（置顶 + 鼠标穿透）", "ok")

            self.engine_thread = threading.Thread(
                target=self._run_engine, daemon=True, name="engine-loop"
            )
            self.engine_thread.start()

            if not self.ready.wait(timeout=180):
                if self._stop_requested:
                    return
                raise RuntimeError("启动超时：OCR 模型加载过久")
            if self._stop_requested:
                self._stop_impl()
                return

            with self.lock:
                self.running = True
                self.starting = False
                self.started_at = time.time()
                self.status = "running"
                self.status_text = "实时翻译运行中"
            self.log("翻译服务已启动", "ok")
        except Exception as e:
            with self.lock:
                self.running = False
                self.starting = False
                self.status = "error"
                self.status_text = "启动失败"
                self.last_error = str(e)
            self.log(f"启动失败：{e}", "error")
            self._cleanup()
        finally:
            with self.lock:
                if not self.running:
                    self.starting = False

    def _run_engine(self):
        try:
            asyncio.run(self._amain())
        except Exception as e:
            with self.lock:
                self.last_error = str(e)
                self.status = "error"
                self.status_text = "运行异常"
                self.running = False
            self.log(f"引擎线程异常：{e}", "error")

    async def _amain(self):
        self.loop = asyncio.get_running_loop()
        with self.lock:
            cfg = self.cfg
        relay_task = asyncio.create_task(
            relay_serve(host=cfg.relay_host, port=cfg.relay_port),
            name="relay-server",
        )

        def _relay_done(t):
            if t.cancelled():
                return
            err = t.exception()
            if err:
                self.log(f"中继服务异常：{err}", "error")

        relay_task.add_done_callback(_relay_done)
        await asyncio.sleep(0.25)

        pipe = Pipeline(
            cfg, self.overlay, voice_only=self._voice_only,
            on_subtitle=self._on_subtitle,
            on_stats=self._on_stats,
            on_log=self.log,
            on_peers=self._on_peers,
        )
        with self.lock:
            self.pipeline = pipe
        self.ready.set()
        try:
            await pipe.run()
        finally:
            relay_task.cancel()
            try:
                await relay_task
            except (asyncio.CancelledError, Exception):
                pass
            with self.lock:
                self.pipeline = None

    def _stop_impl(self):
        with self.lock:
            pipe = self.pipeline
            self.status = "stopping"
            self.status_text = "正在停止…"
        self.log("正在停止翻译服务…", "info")
        try:
            self.asr.stop()
        except Exception:
            pass
        if pipe:
            try:
                pipe.stop()
            except Exception:
                pass
        thread = self.engine_thread
        if thread and thread.is_alive():
            thread.join(timeout=8.0)
        self._cleanup()
        with self.lock:
            self.running = False
            self.starting = False
            self.status = "idle"
            self.status_text = "已暂停"
            self.started_at = 0
            self.pipeline = None
            self.loop = None
        self.log("翻译服务已停止", "info")

    def _cleanup(self):
        with self.lock:
            overlay = self.overlay
            phone = self.phone
            self.overlay = None
            self.phone = None
        if overlay:
            try:
                overlay.shutdown()
            except Exception:
                pass
        if phone:
            try:
                phone.stop()
            except Exception:
                pass

    def stop(self) -> dict:
        with self.lock:
            if not self.running and not self.starting:
                return {"ok": True, "already": True}
            self._stop_requested = True
        if self.starting and not self.running:
            # 启动线程会在 ready 后自行收尾
            return {"ok": True, "stopping": True}
        threading.Thread(target=self._stop_impl, daemon=True, name="stop-engine").start()
        return {"ok": True}

    def toggle(self) -> dict:
        with self.lock:
            if self.running:
                return self.stop()
            return self.start()

    # ---------------- 配置 / 应用 ----------------
    def update_config(self, patch: dict) -> dict:
        allowed = set(self.cfg.__dataclass_fields__.keys())
        with self.lock:
            for key, value in (patch or {}).items():
                if key in allowed:
                    setattr(self.cfg, key, value)
            self.cfg.normalize()
            self.cfg.ensure_pair()
            self.cfg.save(self.cfg_path)
            return self.cfg.public()

    def apply_translator(self) -> dict:
        with self.lock:
            cfg = copy.copy(self.cfg)
            pipe = self.pipeline
        self.log(f"应用翻译引擎：{cfg.translator} → {cfg.target_lang}", "info")

        def _work():
            try:
                translator = build_translator(cfg)
                if pipe:
                    pipe.set_translator(translator)
                self.log("翻译引擎已应用", "ok")
            except Exception as e:
                self.log(f"翻译引擎应用失败：{e}", "error")

        threading.Thread(target=_work, daemon=True).start()
        return {"ok": True}

    def apply_vision(self) -> dict:
        with self.lock:
            cfg = copy.copy(self.cfg)
            pipe = self.pipeline
        if not pipe:
            self.log("视觉设置已保存，将在启动后生效", "info")
            return {"ok": True, "deferred": True}
        if getattr(pipe, "voice_only", False):
            self.log("当前是语音模式，屏幕识别未启用；请停止后用「开始翻译」启动完整服务", "info")
            return {"ok": True, "deferred": True, "voice_only": True}
        self.log("正在应用屏幕识别设置…", "info")

        def _work():
            from pc.ocr import build_ocr
            try:
                provider = build_ocr(cfg, lambda m: self.log(m, "info"))
                pipe.set_ocr(provider)
                self.log("屏幕识别设置已生效", "ok")
            except Exception as e:
                self.log(f"OCR 设置应用失败：{e}", "error")

        threading.Thread(target=_work, daemon=True).start()
        return {"ok": True}

    # ---------------- 其他动作 ----------------
    def manual_translate(self, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "内容为空"}
        with self.lock:
            pipe = self.pipeline if self.running else None
            cfg = copy.copy(self.cfg)
        if pipe:
            pipe.submit(text, "manual")
            self.log(f"手动翻译：{text[:48]}", "manual")
            return {"ok": True, "queued": True}
        # 未启动时直接翻译并写入消息流
        from lid import detect
        result = detect(text, target=cfg.target_lang)
        translator = build_translator(cfg)
        translated = translator.translate(result["clean"], result["lang"], cfg.target_lang)
        msg = {
            "id": 0,
            "ts": int(time.time() * 1000),
            "lang": result["lang"],
            "conf": result["confidence"],
            "src": result["clean"] or text,
            "trans": translated or (result["clean"] or text),
            "engine": getattr(translator, "name", "unknown"),
            "source": "manual",
            "degraded": not bool(translated),
            "retry": False,
            "same_lang": not result["need_translate"],
            "mode": "translate" if result["need_translate"] else "transcribe",
        }
        self._on_subtitle(msg)
        return {"ok": True, "message": msg}

    def send_clipboard(self, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "剪贴板内容为空"}
        import pyperclip
        try:
            pyperclip.copy(text)
        except Exception as e:
            return {"ok": False, "error": f"写入剪贴板失败：{e}"}
        with self.lock:
            pipe = self.pipeline if self.running else None
        if pipe:
            pipe.push_clipboard(text)
        self.log(f"剪贴板已写入：{text[:40]}", "clip")
        return {"ok": True}

    def test_overlay(self, text: str) -> dict:
        with self.lock:
            overlay = self.overlay
        if not overlay:
            return {"ok": False, "error": "字幕条未生效，请打开字幕条开关并重新启动服务"}
        overlay.push(text or "字幕条预览 · Lingua Studio", "PREVIEW · 字幕样式")
        return {"ok": True}

    # ---------------- ASR ----------------
    def asr_devices(self) -> dict:
        return self.asr.devices()

    def asr_start(self, device_id: str, model: str, language: str, chunk: float) -> dict:
        with self.lock:
            self.cfg.asr_device_id = device_id or self.cfg.asr_device_id
            self.cfg.asr_model = model or self.cfg.asr_model
            self.cfg.asr_language = language or ""
            self.cfg.asr_chunk = float(chunk or self.cfg.asr_chunk)
            self.cfg.normalize()
            self.cfg.save(self.cfg_path)
        self.log("启动语音识别…", "info")
        return self.asr.start(self.cfg.asr_model, self.cfg.asr_device_id,
                              self.cfg.asr_language, self.cfg.asr_chunk)

    def asr_stop(self) -> dict:
        self.log("停止语音识别", "info")
        return self.asr.stop()

    def asr_prepare(self, model: str) -> dict:
        with self.lock:
            if model:
                self.cfg.asr_model = model
                self.cfg.save(self.cfg_path)
        return self.asr.prepare(model or self.cfg.asr_model)

    def asr_levels(self) -> dict:
        return self.asr.levels()

    def asr_models_state(self) -> dict:
        return {m: self.asr.model_state(m) for m in ("tiny", "base", "small")}

    # ---------------- 其他 ---------------- -
    def phone_qr(self) -> dict:
        return {"url": self.cfg.phone_url, "qr": qr_data_url(self.cfg.phone_url),
                "pair": self.cfg.pair, "ip": get_lan_ip(),
                "ports": {"relay": self.cfg.relay_port, "phone": self.cfg.phone_port}}

    def clear_feed(self):
        with self.lock:
            self.subs.clear()
        self.log("已清空字幕流", "info")

    def shutdown(self):
        """窗口关闭时同步收尾。"""
        try:
            if self.running or self.starting:
                self._stop_impl()
            else:
                self._cleanup()
                try:
                    self.asr.stop()
                except Exception:
                    pass
        except Exception as e:
            log.warning("shutdown: %s", e)

