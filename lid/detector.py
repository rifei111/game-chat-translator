"""
本地语种识别模块（Lingua）
流水线位置：OCR 出新行 -> 清洗 -> 本模块判定语种/置信度 -> 翻译模块

返回结构统一为 dict：
{
  "lang": "en" | "ja" | "ru" | "zh" | ... | "unknown",
  "confidence": 0.0~1.0,
  "clean": "清洗后的正文",
  "need_translate": True/False,   # 已是目标语言则不翻
}
"""
from __future__ import annotations

import re
import threading
from typing import Dict, Optional

from lingua import Language, LanguageDetectorBuilder

# 外服游戏常见语种（按需增删；ISO 639-1 小写）
SUPPORTED = [
    Language.ENGLISH,
    Language.JAPANESE,
    Language.KOREAN,
    Language.RUSSIAN,
    Language.GERMAN,
    Language.FRENCH,
    Language.SPANISH,
    Language.PORTUGUESE,
    Language.TURKISH,
    Language.ARABIC,
    Language.VIETNAMESE,
    Language.THAI,
    Language.CHINESE,
]

# 玩家名前缀分隔符：[Rifei]: / ヤマト： / 【ヤマト】
_PREFIX_SPLIT = re.compile(r"[:：】\]]")
# 只保留字母、CJK、空格；剥掉 emoji / 标点 / 数字 / 符号
_KEEP = re.compile(r"[^A-Za-z\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0400-\u04ff\u0600-\u06ff\s]")
_MULTI_SPACE = re.compile(r"\s+")

# 置信度低于该值判为 unknown（lingua 短句容易虚高，留保守阈值）
CONFIDENCE_THRESHOLD = 0.55

_detector = None
_lock = threading.Lock()


def _get_detector():
    """单例：构建检测器有开销，只建一次。"""
    global _detector
    if _detector is None:
        with _lock:
            if _detector is None:
                _detector = LanguageDetectorBuilder.from_languages(*SUPPORTED).build()
    return _detector


def clean_text(raw: str) -> str:
    """去掉玩家名前缀、emoji、标点、数字，只留可判语种的正文。"""
    if not raw:
        return ""
    text = raw.strip()
    # 截掉名字前缀
    if _PREFIX_SPLIT.search(text):
        text = _PREFIX_SPLIT.split(text, maxsplit=1)[1]
    text = _KEEP.sub(" ", text)
    text = _MULTI_SPACE.sub(" ", text).strip()
    return text


def _iso(lang: Language) -> str:
    return lang.iso_code_639_1.name.lower()


_LATIN_ONLY = re.compile(r"^[A-Za-z0-9 '\-_.!?,]+$")
SHORT_TEXT_LEN = 8      # 短文本（<8 字符）提高阈值，避免 ok/gg 被误判成小语种


def detect(raw: str, target: str = "zh") -> Dict:
    """
    判定一行聊天文本的语种。
    target: 目标语言代码（默认 zh），检测结果等于 target 时 need_translate=False。
    """
    clean = clean_text(raw)

    # 太短 / 空：不送检测
    if len(clean) < 2:
        return {"lang": "unknown", "confidence": 0.0, "clean": clean,
                "need_translate": False, "guessed": False}

    detector = _get_detector()
    vals = detector.compute_language_confidence_values(clean)
    if not vals:
        return {"lang": "unknown", "confidence": 0.0, "clean": clean,
                "need_translate": True, "guessed": False}

    best = max(vals, key=lambda x: x.value)
    best_lang = best.language
    confidence = float(best.value)
    lang_code = _iso(best_lang)
    guessed = False

    # 短文本提高阈值：ok/gg/lol 这类短词 lingua 容易误判成小语种
    threshold = CONFIDENCE_THRESHOLD
    if len(clean) < SHORT_TEXT_LEN:
        threshold = 0.70

    if confidence < threshold:
        # 纯拉丁字母且有一定长度 -> 按英文处理（游戏里拉丁短句绝大多数是英语）
        if _LATIN_ONLY.match(clean) and len(clean) >= 3:
            lang_code = "en"
            guessed = True
        else:
            lang_code = "unknown"

    need_translate = lang_code != target
    # 超短且判不出语种（"ok"/"gg"/"+"）：当噪声跳过，不推字幕
    if lang_code == "unknown" and len(clean) <= 3:
        need_translate = False

    return {
        "lang": lang_code,
        "confidence": round(confidence, 3),
        "clean": clean,
        "need_translate": need_translate,
        "guessed": guessed,
    }


def detect_many(lines: list[str], target: str = "zh") -> list[Dict]:
    return [detect(line, target) for line in lines]
