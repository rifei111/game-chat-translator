"""
剪贴板读写 + 变化检测。
- 本地剪贴板变化 -> 上报给手机端
- 收到手机端剪贴板 -> 写入本地，并标记避免回环
"""
from __future__ import annotations

import time
import pyperclip


class Clipboard:
    def __init__(self):
        self._last = ""
        self._remote_pending = ""  # 刚从远端写入的内容，不回推

    def get(self) -> str:
        try:
            return pyperclip.paste().strip()
        except Exception:
            return ""

    def set(self, text: str):
        self._remote_pending = text
        try:
            pyperclip.copy(text)
        except Exception:
            pass
        self._last = text

    def poll_changed(self) -> str | None:
        """轮询剪贴板；有新内容返回文本，否则 None。忽略刚从远端写入的内容。"""
        cur = self.get()
        if not cur or cur == self._last:
            return None
        if cur == self._remote_pending:
            self._remote_pending = ""
            self._last = cur
            return None
        self._last = cur
        return cur
