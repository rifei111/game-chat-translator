"""PC 端配置：局域网模式，自动探测本机 IP，首次运行生成 config.json。"""
from __future__ import annotations

import json
import os
import secrets
import socket
from dataclasses import dataclass, asdict, field


def get_lan_ip() -> str:
    """探测本机局域网 IPv4（手机端要填的地址）。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@dataclass
class Config:
    # 中继 / 手机端服务（局域网，无需公网）
    relay_host: str = "0.0.0.0"
    relay_port: int = 8780
    phone_port: int = 8781

    # 配对：PC 与手机必须一致，留空则自动生成
    pair: str = ""

    # 翻译
    target_lang: str = "zh"
    translator: str = "mock"      # mock | argos | deepl | qwen
    deepl_key: str = ""
    qwen_key: str = ""

    # OCR
    ocr_source: str = "screen"    # screen | demo
    region: list = field(default_factory=lambda: [80, 480, 620, 200])
    ocr_min_score: float = 0.62
    ocr_line_gap: int = 14        # 同一行的 y 容差（像素）
    min_text_len: int = 2

    # 流水线
    poll_interval: float = 1.5    # 抓取间隔（秒）
    dedup_window: float = 8.0     # 相同文本忽略窗口（秒）

    # 字幕覆盖层
    overlay: bool = True
    overlay_height: int = 110
    overlay_font: int = 22
    subtitle_ttl: float = 8.0

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

    # ---- 读写 ----
    @classmethod
    def load(cls, path: str = "config.json") -> "Config":
        data = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        allowed = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        cfg = cls(**allowed)
        if "region" in allowed:
            cfg.region = list(cfg.region)
        return cfg

    def save(self, path: str = "config.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)
