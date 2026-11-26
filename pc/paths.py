"""路径适配：开发态用源码目录，打包后用 exe 旁的 data/ 保存用户数据。"""
from __future__ import annotations

import os
import sys


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(rel: str = "") -> str:
    """只读资源：打包后位于 PyInstaller 解包目录。"""
    base = getattr(sys, "_MEIPASS", app_dir())
    return os.path.join(base, rel) if rel else base


def data_dir() -> str:
    path = os.path.join(app_dir(), "data")
    os.makedirs(path, exist_ok=True)
    return path


def model_dir() -> str:
    path = os.path.join(data_dir(), "models")
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def ui_path(*parts: str) -> str:
    return os.path.join(resource_path("ui"), *parts)


def phone_path(*parts: str) -> str:
    return os.path.join(resource_path("phone"), *parts)


def asset_path(*parts: str) -> str:
    return os.path.join(resource_path("assets"), *parts)
