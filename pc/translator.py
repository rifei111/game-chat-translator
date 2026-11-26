"""翻译层：mock / free（MyMemory 免费在线） / argos / deepl / qwen。"""
from __future__ import annotations

import html
import logging
import math
import re
import threading
from typing import Protocol

log = logging.getLogger("translate")

DEEPL_LANG = {
    "en": "EN", "ja": "JA", "ko": "KO", "ru": "RU", "de": "DE",
    "fr": "FR", "es": "ES", "pt": "PT", "it": "IT", "zh": "ZH",
    "tr": "TR", "ar": "AR", "vi": "VI", "th": "TH",
}

# MyMemory 语言码
MEM_LANG = {
    "zh": "zh-CN", "en": "en", "ja": "ja", "ko": "ko", "ru": "ru",
    "de": "de", "fr": "fr", "es": "es", "pt": "pt", "it": "it",
    "ar": "ar", "tr": "tr", "vi": "vi", "th": "th", "id": "id",
    "nl": "nl", "pl": "pl", "sv": "sv", "uk": "uk",
}

_MEM_BAD = (
    "PLEASE SELECT TWO DISTINCT",
    "MYMEMORY WARNING",
    "QUERY LENGTH LIMIT",
    "INVALID LANGUAGE PAIR",
    "NO QUERY SPECIFIED",
    "YOU USED ALL AVAILABLE FREE TRANSLATIONS",
)


class Translator(Protocol):
    name: str

    def translate(self, text: str, src: str, target: str) -> str:
        ...


class MockTranslator:
    name = "mock"

    def translate(self, text: str, src: str, target: str) -> str:
        return f"[{src}→{target}] {text}"


class FreeTranslator:
    """MyMemory 免费在线翻译，无需 API Key。

    - 游戏聊天通常很短，一次请求即可；
    - 长文本按 450 字符切段，避免触发 500 字节限制；
    - 失败返回空串，由流水线保留原文。
    """

    name = "free"
    ENDPOINT = "https://api.mymemory.translated.net/get"

    def __init__(self):
        self.last_error = ""

    @staticmethod
    def _chunks(text: str, limit: int = 420) -> list[str]:
        text = text.strip()
        if len(text) <= limit:
            return [text]
        parts = re.split(r"(?<=[.!?。！？；;])\s+", text)
        chunks, cur = [], ""
        for part in parts:
            if not part:
                continue
            if len(cur) + len(part) + 1 <= limit:
                cur = f"{cur} {part}".strip()
            else:
                if cur:
                    chunks.append(cur)
                while len(part) > limit:
                    chunks.append(part[:limit])
                    part = part[limit:]
                cur = part
        if cur:
            chunks.append(cur)
        return chunks

    def translate(self, text: str, src: str, target: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        if src == target:
            return text
        src_code = MEM_LANG.get(src) or "en"
        tgt_code = MEM_LANG.get(target) or "zh-CN"
        import requests

        out: list[str] = []
        try:
            for chunk in self._chunks(text):
                if not chunk.strip():
                    continue
                params = {"q": chunk, "langpair": f"{src_code}|{tgt_code}"}
                r = requests.get(
                    self.ENDPOINT,
                    params=params,
                    timeout=10,
                    headers={"User-Agent": "LinguaStudio/1.0"},
                )
                if r.status_code != 200:
                    self.last_error = f"HTTP {r.status_code}"
                    return ""
                data = r.json()
                translated = html.unescape(
                    str((data.get("responseData") or {}).get("translatedText") or "")
                ).strip()
                if not translated:
                    self.last_error = "empty response"
                    return ""
                if any(bad in translated.upper() for bad in _MEM_BAD):
                    self.last_error = translated[:80]
                    return ""
                out.append(translated)
            self.last_error = ""
            return " ".join(out).strip()
        except Exception as e:
            self.last_error = str(e)
            log.warning("免费翻译失败：%s", e)
            return ""


class ArgosTranslator:
    """本地离线翻译（argostranslate）；缺包时返回空串并后台下载。"""

    name = "argos"
    PREFETCH_SRC = ("en", "ja", "ko", "ru", "de", "fr", "es", "pt")

    def __init__(self, target: str = "zh"):
        self.target = target
        self._err = ""
        self._thread = None
        self._lock = threading.Lock()
        self._tr = None
        self._start_prefetch()

    def _start_prefetch(self):
        self._thread = threading.Thread(target=self._prefetch, daemon=True)
        self._thread.start()

    def _prefetch(self):
        try:
            import argostranslate.translate as tr
            self._tr = tr
            installed = {l.code for l in tr.get_installed_languages()}
            if self.target in installed:
                return
            import argostranslate.package as pkg
            pkg.update_package_index()
            for p in pkg.get_available_packages():
                if p.to_code == self.target and p.from_code in self.PREFETCH_SRC:
                    log.info("后台下载语言包 %s→%s（首次较慢）", p.from_code, p.to_code)
                    try:
                        pkg.install_from_path(p.download())
                        log.info("语言包就绪 %s→%s", p.from_code, p.to_code)
                    except Exception as e:
                        log.warning("语言包 %s→%s 失败：%s", p.from_code, p.to_code, e)
        except Exception as e:
            self._err = str(e)
            log.warning("argos 预取失败：%s", e)

    def translate(self, text: str, src: str, target: str) -> str:
        tr = self._tr
        if tr is None:
            return ""
        try:
            installed = {l.code: l for l in tr.get_installed_languages()}
            fl = installed.get(src) or installed.get("en")
            tl = installed.get(target)
            if not fl or not tl:
                return ""
            path = fl.get_translation(tl)
            if not path:
                return ""
            with self._lock:
                return path.translate(text)
        except Exception as e:
            log.warning("argos 翻译失败：%s", e)
            return ""


class DeeplTranslator:
    name = "deepl"

    def __init__(self, key: str):
        self.key = key

    def translate(self, text: str, src: str, target: str) -> str:
        if not self.key:
            return ""
        import requests
        host = "api-free.deepl.com" if self.key.endswith(":fx") else "api.deepl.com"
        try:
            r = requests.post(
                f"https://{host}/v2/translate",
                headers={"Authorization": f"DeepL-Auth-Key {self.key}"},
                data={
                    "text": text,
                    "target_lang": DEEPL_LANG.get(target, "ZH"),
                    "source_lang": DEEPL_LANG.get(src, ""),
                },
                timeout=10,
            )
            if r.status_code != 200:
                log.warning("DeepL %s: %s", r.status_code, r.text[:120])
                return ""
            return r.json()["translations"][0]["text"]
        except Exception as e:
            log.warning("DeepL 失败：%s", e)
            return ""


class QwenTranslator:
    """阿里云百炼兼容模式（qwen-turbo），OpenAI 协议。"""

    name = "qwen"

    def __init__(self, key: str, model: str = "qwen-turbo"):
        self.key = key
        self.model = model

    def translate(self, text: str, src: str, target: str) -> str:
        if not self.key:
            return ""
        import requests
        lang_name = {"zh": "简体中文", "en": "English", "ja": "日本語"}.get(target, target)
        try:
            r = requests.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system",
                         "content": f"你是游戏聊天翻译。把用户输入翻译成{lang_name}，"
                                    f"只输出译文，不要解释、不要引号。"},
                        {"role": "user", "content": text},
                    ],
                    "temperature": 0.2,
                },
                timeout=15,
            )
            if r.status_code != 200:
                log.warning("qwen %s: %s", r.status_code, r.text[:120])
                return ""
            return r.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log.warning("qwen 失败：%s", e)
            return ""


def build_translator(cfg) -> Translator:
    kind = cfg.translator
    if kind == "argos":
        return ArgosTranslator(cfg.target_lang)
    if kind == "deepl":
        return DeeplTranslator(cfg.deepl_key)
    if kind == "qwen":
        return QwenTranslator(cfg.qwen_key)
    if kind == "mock":
        return MockTranslator()
    return FreeTranslator()
