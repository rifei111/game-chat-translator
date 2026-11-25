"""
PC 端主流水线：
OCR 抓取 -> 行级去重 -> 本地语种识别 -> 翻译 -> 中继推送 + 字幕覆盖层
同时监听中继：手机端剪贴板写回本机、手机端发起重译。
"""
from __future__ import annotations

import asyncio
import logging
import re
import threading
import time

from lid import detect
from .ocr import build_ocr
from .translator import build_translator
from .clip import Clipboard
from .relay_client import RelayClient

log = logging.getLogger("pipeline")

_NORM = re.compile(r"[^a-z0-9\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff]")
_PUNCT_ONLY = re.compile(r"^[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+$")


def _norm(text: str) -> str:
    return _NORM.sub("", text.lower())


class Pipeline:
    def __init__(self, cfg, overlay=None):
        self.cfg = cfg
        self.ocr = build_ocr(cfg)
        self.translator = build_translator(cfg)
        self.clip = Clipboard()
        self.overlay = overlay
        self._seen: dict[str, float] = {}
        self.relay = RelayClient(cfg.relay_url, cfg.pair, "pc", self._on_relay)
        self.stats = {"ocr_lines": 0, "pushed": 0, "skipped": 0}

    # ---- 对外 ----
    async def run(self):
        await asyncio.gather(self.relay.run(), self._loop())

    def _send(self, msg: dict):
        """有事件循环就调度协程；同步环境开线程兜底。"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.relay.send(msg))
        except RuntimeError:
            threading.Thread(
                target=lambda: asyncio.run(self.relay.send(msg)), daemon=True
            ).start()

    # ---- 主循环 ----
    async def _loop(self):
        while True:
            try:
                self._poll_ocr()
                self._poll_clipboard()
            except Exception as e:
                log.warning("循环异常：%s", e)
            await asyncio.sleep(self.cfg.poll_interval)

    def _poll_ocr(self):
        try:
            lines = self.ocr.read_lines()
        except Exception as e:
            log.warning("OCR 失败：%s", e)
            return
        for line in lines:
            self.stats["ocr_lines"] += 1
            self._handle_line(line)

    def _handle_line(self, raw: str):
        raw = (raw or "").strip()
        if len(raw) < self.cfg.min_text_len:
            return
        if _PUNCT_ONLY.match(raw):
            return

        key = _norm(raw)
        if not key:
            return
        now = time.time()
        if now - self._seen.get(key, 0) < self.cfg.dedup_window:
            self.stats["skipped"] += 1
            return
        self._seen[key] = now
        # 控制内存：清掉过期键
        if len(self._seen) > 4000:
            cutoff = now - self.cfg.dedup_window * 2
            self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}

        result = detect(raw, target=self.cfg.target_lang)
        if not result["need_translate"]:
            self.stats["skipped"] += 1
            return

        translated = self.translator.translate(
            result["clean"], result["lang"], self.cfg.target_lang
        )
        if not translated:
            translated = result["clean"]  # 翻译失败保留原文，不丢消息

        msg = {
            "type": "subtitle",
            "ts": int(now * 1000),
            "lang": result["lang"],
            "conf": result["confidence"],
            "src": result["clean"],
            "trans": translated,
            "engine": getattr(self.translator, "name", "unknown"),
        }
        self.stats["pushed"] += 1
        self._send(msg)
        if self.overlay:
            self.overlay.push(translated)
        log.info("[%s] %s -> %s", result["lang"], result["clean"], translated)

    def _poll_clipboard(self):
        text = self.clip.poll_changed()
        if text:
            log.info("本机剪贴板变化，推送到手机：%s", text[:30])
            self._send({"type": "clipboard", "text": text, "from": "pc"})

    # ---- 中继消息 ----
    def _on_relay(self, msg: dict):
        mtype = msg.get("type")
        if mtype == "clipboard":
            text = msg.get("text", "")
            log.info("收到手机剪贴板，写入本机：%s", text[:30])
            self.clip.set(text)
        elif mtype == "translate_request":
            src = msg.get("src", "")
            lang = msg.get("lang", "unknown")
            translated = self.translator.translate(src, lang, self.cfg.target_lang)
            self._send({
                "type": "subtitle", "ts": int(time.time() * 1000),
                "lang": lang, "src": src, "trans": translated or src,
                "retry": True,
                "engine": getattr(self.translator, "name", "unknown"),
            })
        elif mtype == "status_request":
            self._send({"type": "status", **self.stats, "engine":
                        getattr(self.translator, "name", "unknown")})
        elif mtype in ("paired", "peer_joined", "peer_left"):
            log.info("中继：%s", msg)
