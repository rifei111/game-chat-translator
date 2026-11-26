"""Lingua Studio 配置：局域网中继、OCR、翻译、语音识别与界面偏好。"""
from __future__ import annotations

import json
import os
import secrets
import socket
from dataclasses import asdict, dataclass, field


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


TARGET_LANGS = {
    "zh": "简体中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "ru": "Русский",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "pt": "Português",
    "ar": "العربية",
    "tr": "Türkçe",
    "vi": "Tiếng Việt",
    "th": "ไทย",
}

OCR_LANGS = {
    "auto": {"label": "自动多语", "hint": "中 / 日 / 英 / 欧洲语言", "engine": "PP-OCRv6 multi"},
    "ch": {"label": "中文 + 英文", "hint": "默认高精度", "engine": "PP-OCRv6 multi"},
    "japan": {"label": "日语", "hint": "かな / 汉字", "engine": "PP-OCRv4 japan"},
    "korean": {"label": "韩语", "hint": "한국어", "engine": "PP-OCRv4 korean"},
    "cyrillic": {"label": "俄语 / 西里尔", "hint": "Русский", "engine": "PP-OCRv4 cyrillic"},
    "latin": {"label": "欧洲语言", "hint": "DE / FR / ES / PT", "engine": "PP-OCRv4 latin"},
    "arabic": {"label": "阿拉伯语", "hint": "العربية", "engine": "PP-OCRv4 arabic"},
}

ASR_MODELS = {
    "tiny": {"label": "Tiny", "size": "约 75 MB", "hint": "最快，准确率一般"},
    "base": {"label": "Base", "size": "约 145 MB", "hint": "均衡，推荐"},
    "small": {"label": "Small", "size": "约 484 MB", "hint": "更准，CPU 稍慢"},
}


@dataclass
class Config:
    # 中继 / 手机端（纯局域网）
    relay_host: str = "0.0.0.0"
    relay_port: int = 8780
    phone_port: int = 8781
    pair: str = ""

    # 翻译
    target_lang: str = "zh"
    translator: str = "free"      # mock | free | argos | deepl | qwen
    deepl_key: str = ""
    qwen_key: str = ""

    # OCR
    ocr_source: str = "demo"      # demo | screen
    region: list = field(default_factory=lambda: [80, 900, 900, 320])
    ocr_lang: str = "auto"
    ocr_min_score: float = 0.62
    ocr_line_gap: int = 14
    min_text_len: int = 2

    # 流水线
    poll_interval: float = 1.5
    dedup_window: float = 8.0
    show_same_language: bool = False

    # PC 字幕条
    overlay: bool = True
    overlay_height: int = 118
    overlay_font: int = 23
    overlay_radius: int = 26
    subtitle_ttl: float = 8.0
    overlay_opacity: float = 0.88

    # 剪贴板 / 手机
    clipboard_sync: bool = True

    # 语音识别（Whisper）
    asr_model: str = "base"
    asr_device_id: str = ""
    asr_device_name: str = "系统声音（扬声器回环）"
    asr_language: str = ""        # 空 = 自动
    asr_chunk: float = 5.0
    asr_translate: bool = True

    # 界面
    theme: str = "dark"
    accent: str = "blue"
    particles: bool = True
    particle_density: int = 70
    reduce_motion: bool = False
    window_width: int = 1340
    window_height: int = 860

    # ---- 便捷方法 ----
    def ensure_pair(self) -> str:
        if not self.pair:
            self.pair = secrets.token_hex(3).upper()
        return self.pair

    @property
    def relay_url(self) -> str:
        return f"ws://{get_lan_ip()}:{self.relay_port}"

    @property
    def phone_url(self) -> str:
        ip = get_lan_ip()
        return (f"http://{ip}:{self.phone_port}/"
                f"?relay=ws://{ip}:{self.relay_port}&pair={self.pair}")

    def normalize(self):
        self.relay_port = int(self.relay_port)
        self.phone_port = int(self.phone_port)
        if self.ocr_lang not in OCR_LANGS:
            self.ocr_lang = "auto"
        if self.asr_model not in ASR_MODELS:
            self.asr_model = "base"
        self.poll_interval = max(0.5, min(10.0, float(self.poll_interval)))
        self.dedup_window = max(1.0, min(120.0, float(self.dedup_window)))
        self.asr_chunk = max(2.0, min(15.0, float(self.asr_chunk)))
        self.overlay_font = max(14, min(48, int(self.overlay_font)))
        self.overlay_height = max(64, min(260, int(self.overlay_height)))
        self.overlay_radius = max(8, min(40, int(self.overlay_radius)))
        self.overlay_opacity = max(0.3, min(1.0, float(self.overlay_opacity)))
        self.particle_density = max(0, min(200, int(self.particle_density)))
        self.ocr_min_score = max(0.2, min(0.99, float(self.ocr_min_score)))
        if len(self.region or []) != 4:
            self.region = [80, 900, 900, 320]
        self.region = [int(v) for v in self.region]
        return self

    # ---- 读写 ----
    @classmethod
    def load(cls, path: str) -> "Config":
        data = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        allowed = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        cfg = cls(**allowed)
        return cfg.normalize()

    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    def public(self) -> dict:
        """给前端的配置副本（API key 返回，方便本地编辑；日志中不打印）。"""
        return asdict(self)
