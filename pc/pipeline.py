"""PC 流水线：OCR / 语音 / 手动文本 -> 去重 -> 语种 -> 翻译 -> 字幕条 + 中继。"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Callable

from lid import detect
from .clip import Clipboard
from .relay_client import RelayClient
from .translator import build_translator

log = logging.getLogger("pipeline")

_NORM = re.compile(r"[^a-z0-9\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff]")
_PUNCT_ONLY = re.compile(r"^[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+$")

LANG_LABEL = {
    "en": "EN", "ja": "JA", "ko": "KO", "ru": "RU", "de": "DE",
    "fr": "FR", "es": "ES", "pt": "PT", "it": "IT", "zh": "中文",
    "tr": "TR", "ar": "AR", "vi": "VI", "th": "TH", "unknown": "??",
}
TARGET_LABEL = {
    "zh": "中文", "en": "English", "ja": "日本語", "ko": "한국어",
    "ru": "Русский", "de": "Deutsch", "fr": "Français", "es": "Español",
    "pt": "Português", "ar": "العربية", "tr": "Türkçe", "vi": "Tiếng Việt",
    "th": "ไทย",
}


def _norm(text: str) -> str:
    return _NORM.sub("", text.lower())


class Pipeline:
    def __init__(self, cfg, overlay, on_subtitle: Callable[[dict], None],
                 on_stats: Callable[[dict], None], on_log: Callable[[str, str], None],
                 on_peers: Callable[[int], None], voice_only: bool = False):
        self.cfg = cfg
        self.overlay = overlay
        self.voice_only = bool(voice_only)
        self.on_subtitle = on_subtitle
        self.on_stats = on_stats
        self.on_log = on_log
        self.on_peers = on_peers

        self.ocr = None
        self.translator = build_translator(cfg)
        self.clip = Clipboard()
        self.relay = RelayClient(cfg.relay_url, cfg.pair, "pc", self._on_relay)
        self.queue: asyncio.Queue | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stop_event: asyncio.Event | None = None
        self._seen: dict[str, float] = {}
        self._seq = 0
        self.peers = 0
        self.stats = {"ocr_lines": 0, "pushed": 0, "skipped": 0, "asr_segments": 0}
        self._last_clip_out = ""
        self._status_task = None

    # ---- 生命周期 ----
    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self.stop_event = asyncio.Event()
        if self.voice_only:
            self.ocr = None
            self.on_log("语音模式已就绪 · 屏幕识别未启用", "ok")
        else:
            from .ocr import build_ocr
            self.ocr = build_ocr(self.cfg, lambda msg: self.on_log(msg, "info"))
            self.on_log("流水线已就绪", "ok")
        self._status_task = asyncio.create_task(self._status_loop())
        tasks = [
            asyncio.create_task(self.relay.run()),
            asyncio.create_task(self._queue_worker()),
        ]
        if not self.voice_only:
            tasks.append(asyncio.create_task(self._ocr_loop()))
        try:
            await self.stop_event.wait()
        finally:
            for task in tasks + [self._status_task]:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
            self.relay.stop()
            self.on_log("流水线已停止", "info")

    async def _status_loop(self):
        while not self.stop_event.is_set():
            await asyncio.sleep(2.0)
            self._send({"type": "status", **self.stats,
                        "engine": getattr(self.translator, "name", "unknown")})

    def stop(self):
        if self.loop and self.stop_event:
            self.loop.call_soon_threadsafe(self.stop_event.set)

    def submit(self, text: str, source: str = "manual", lang: str = "", conf: float = 0.0,
               translate: bool = True):
        """线程安全：ASR 线程 / GUI API 都可以提交一句话。"""
        if not self.loop or not self.queue or not text:
            return False
        item = {"text": str(text), "source": source, "lang": lang,
                "conf": conf, "translate": translate}
        try:
            asyncio.run_coroutine_threadsafe(self.queue.put(item), self.loop)
            return True
        except Exception:
            return False

    def set_ocr(self, provider):
        self.ocr = provider

    def set_translator(self, translator):
        self.translator = translator
        self.on_log(f"翻译引擎已切换：{getattr(translator, 'name', 'unknown')}", "info")

    def push_clipboard(self, text: str):
        if text:
            self._send({"type": "clipboard", "text": text, "from": "pc"})

    def snapshot(self) -> dict:
        return {**self.stats, "peers": self.peers,
                "relay_online": self.relay.connected,
                "engine": getattr(self.translator, "name", "unknown")}

    # ---- 中继 ----
    def _send(self, msg: dict):
        if not self.loop:
            return
        self.loop.create_task(self.relay.send(msg))

    def _on_relay(self, msg: dict):
        mtype = msg.get("type")
        if mtype == "clipboard":
            text = msg.get("text", "")
            if self.cfg.clipboard_sync:
                self.clip.set(text)
            self.on_log(f"手机剪贴板 → 本机：{text[:40]}", "clip")
        elif mtype == "translate_request":
            src = (msg.get("src") or "").strip()
            lang = msg.get("lang") or ""
            if src:
                self.on_log(f"手机请求翻译：{src[:40]}", "relay")
                self.submit(src, source="retry", lang=lang)
        elif mtype == "status_request":
            self._send({"type": "status", **self.snapshot()})
        elif mtype == "paired":
            # peers 含 PC 自己，手机数要减 1
            self.peers = max(0, int(msg.get("peers") or 0) - 1)
            self.on_peers(self.peers)
            self.on_log(f"中继已配对，手机在线 {self.peers} 台", "ok")
        elif mtype == "peer_joined":
            self.peers += 1
            self.on_peers(self.peers)
            self.on_log(f"手机端已加入（{self.peers} 端在线）", "ok")
        elif mtype == "peer_left":
            self.peers = max(0, self.peers - 1)
            self.on_peers(self.peers)
            self.on_log("手机端已断开", "warn")
        elif mtype == "error":
            self.on_log(f"中继错误：{msg.get('msg')}", "warn")

    # ---- 主循环 ----
    async def _ocr_loop(self):
        while not self.stop_event.is_set():
            try:
                lines = await asyncio.to_thread(self.ocr.read_lines)
                if lines:
                    self.stats["ocr_lines"] += len(lines)
                    self.on_stats(self.stats)
                for line in lines:
                    await self._process(line, "ocr")
                if self.cfg.clipboard_sync:
                    text = await asyncio.to_thread(self.clip.poll_changed)
                    if text:
                        await self._send_clipboard(text)
            except Exception as e:
                self.on_log(f"OCR 循环异常：{e}", "error")
                log.warning("OCR loop: %s", e)
            await asyncio.sleep(max(0.5, float(self.cfg.poll_interval)))

    async def _queue_worker(self):
        while not self.stop_event.is_set():
            item = await self.queue.get()
            try:
                await self._process(item["text"], item["source"],
                                    item.get("lang") or "", float(item.get("conf") or 0),
                                    bool(item.get("translate", True)))
            except Exception as e:
                self.on_log(f"文本处理异常：{e}", "error")

    async def _process(self, raw: str, source: str, lang_hint: str = "", conf: float = 0.0,
                       translate: bool = True):
        raw = (raw or "").strip()
        if len(raw) < max(1, int(self.cfg.min_text_len)):
            return
        if _PUNCT_ONLY.match(raw):
            return

        key = _norm(raw)
        if not key:
            return
        now = time.time()
        if now - self._seen.get(key, 0) < self.cfg.dedup_window:
            self.stats["skipped"] += 1
            self.on_stats(self.stats)
            return
        self._seen[key] = now
        if len(self._seen) > 4000:
            cutoff = now - self.cfg.dedup_window * 2
            self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}

        if lang_hint and lang_hint not in ("unknown", ""):
            clean = raw.strip() if source in ("asr", "manual", "retry") else (detect.clean_text(raw) or raw.strip())
            lang = lang_hint
            confidence = round(float(conf) or 1.0, 3)
            need = translate and lang != self.cfg.target_lang
        else:
            result = detect(raw, target=self.cfg.target_lang)
            clean = result["clean"] or raw.strip()
            lang = result["lang"]
            confidence = result["confidence"]
            need = translate and result["need_translate"]

        if not need and source == "ocr" and not self.cfg.show_same_language:
            self.stats["skipped"] += 1
            self.on_stats(self.stats)
            return

        if source == "asr":
            self.stats["asr_segments"] += 1
            self.on_stats(self.stats)

        translated = ""
        degraded = False
        if need:
            translated = await asyncio.to_thread(
                self.translator.translate, clean, lang, self.cfg.target_lang
            )
            if not translated:
                translated = clean
                degraded = True

        if not translated:
            translated = clean

        self._seq += 1
        msg = {
            "id": self._seq,
            "type": "subtitle",
            "ts": int(now * 1000),
            "lang": lang,
            "conf": confidence,
            "src": clean,
            "trans": translated,
            "engine": getattr(self.translator, "name", "unknown"),
            "source": source,
            "degraded": degraded,
            "retry": source == "retry",
            "same_lang": not need,
            "mode": "translate" if need else "transcribe",
        }
        self.stats["pushed"] += 1
        self.on_subtitle(msg)
        self.on_stats(self.stats)
        self._send(msg)

        if self.overlay:
            meta = (f"{LANG_LABEL.get(lang, lang.upper())} → "
                    f"{TARGET_LABEL.get(self.cfg.target_lang, self.cfg.target_lang)}"
                    f"  ·  {'语音' if source == 'asr' else ('重译' if source == 'retry' else '实时翻译')}")
            try:
                self.overlay.push(translated, meta)
            except Exception:
                pass

        log.info("[%s/%s] %s -> %s", source, lang, clean, translated)

    async def _send_clipboard(self, text: str):
        if not text or text == self._last_clip_out:
            return
        self._last_clip_out = text
        self._send({"type": "clipboard", "text": text, "from": "pc"})
        self.on_log(f"本机剪贴板 → 手机：{text[:40]}", "clip")
