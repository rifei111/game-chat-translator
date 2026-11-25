"""
翻译层：mock / argos（本地离线） / deepl / qwen（在线，需 key）。
统一接口 translate(text, src, target) -> str，失败返回空串由上层保留原文。
"""
from __future__ import annotations

import logging
import threading
from typing import Protocol

log = logging.getLogger("translate")

# lingua ISO 639-1 -> Argos / DeepL 语言码
DEEPL_LANG = {
    "en": "EN", "ja": "JA", "ko": "KO", "ru": "RU", "de": "DE",
    "fr": "FR", "es": "ES", "pt": "PT", "it": "IT", "zh": "ZH",
    "tr": "TR", "ar": "AR", "vi": "VI", "th": "TH",
}


class Translator(Protocol):
    name: str

    def translate(self, text: str, src: str, target: str) -> str:
        ...


class MockTranslator:
    name = "mock"

    def translate(self, text: str, src: str, target: str) -> str:
        return f"[{src}→{target}] {text}"


class ArgosTranslator:
    """本地离线翻译（argostranslate）。

    首次使用某语言对会缺模型包：包下载放到后台线程做，不阻塞流水线；
    下载完成前该语种返回空串（上层保留原文），下一条就能正常翻译。
    """

    name = "argos"

    # 目标为中文时优先准备这些源语言（游戏聊天以英语最多）
    PREFETCH_SRC = ("en", "ja", "ko", "ru", "de", "fr", "es", "pt")

    def __init__(self, target: str = "zh"):
        self.target = target
        self._err = ""
        self._thread = None
        self._lock = threading.Lock()
        self._tr = None          # 后台线程导入好的 argostranslate.translate 模块
        self._start_prefetch()

    def _start_prefetch(self):
        self._thread = threading.Thread(target=self._prefetch, daemon=True)
        self._thread.start()

    def _prefetch(self):
        try:
            import argostranslate.translate as tr
            self._tr = tr            # 先给模块引用，import 开销不落在流水线上
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
            return ""  # 模块还没导入完，保留原文
        try:
            installed = {l.code: l for l in tr.get_installed_languages()}
            fl = installed.get(src) or installed.get("en")
            tl = installed.get(target)
            if not fl or not tl:
                return ""  # 模型未就绪，保留原文，等后台下载完
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
    """阿里云百炼 兼容模式（qwen-turbo），OpenAI 协议。"""

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
    return MockTranslator()
