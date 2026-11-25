"""冻结/打包后的路径适配：

- 只读资源（phone 网页、模型数据）走 PyInstaller 解包目录 `sys._MEIPASS`；
- 可写数据（config.json）放 exe 同级目录，避免 onefile 解包目录只读。
开发模式下两者都是项目根目录。
"""
from __future__ import annotations

import os
import sys


def resource_path(rel: str = "") -> str:
    base = getattr(
        sys, "_MEIPASS",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    return os.path.join(base, rel) if rel else base


def data_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_path(name: str = "config.json") -> str:
    return os.path.join(data_dir(), name)
