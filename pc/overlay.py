"""
字幕覆盖层：tkinter 无边框、置顶、半透明、鼠标穿透，只显示一条译文字幕。
tkinter 随 Windows Python 自带，无需额外安装。非 Windows / 无显示环境自动跳过。
"""
from __future__ import annotations

import logging
import queue
import sys
import threading

log = logging.getLogger("overlay")


def _enable_click_through(root):
    """Windows 下让窗口鼠标穿透（点击落到下面的游戏窗口）。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id()) or root.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x00080000
        WS_EX_TRANSPARENT = 0x00000020
        WS_EX_TOOLWINDOW = 0x00000080
        cur = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(
            hwnd, GWL_EXSTYLE, cur | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
        )
    except Exception as e:
        log.warning("设置鼠标穿透失败：%s", e)


class SubtitleOverlay:
    def __init__(self, height: int = 110, font_size: int = 22, ttl: float = 8.0):
        import tkinter as tk
        self.ttl_ms = int(ttl * 1000)
        self.height = height
        self._q: queue.Queue[str] = queue.Queue()

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)
        self.root.configure(bg="#0a0a12")

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        y = max(0, sh - height - 90)
        self.root.geometry(f"{sw}x{height}+0+{y}")

        self.label = tk.Label(
            self.root, text="", bg="#0a0a12", fg="#ffffff",
            font=("Microsoft YaHei", font_size), wraplength=sw - 80,
            justify="center",
        )
        self.label.pack(expand=True, fill="both", padx=30)
        self.root.withdraw()
        _enable_click_through(self.root)

        self._hide_job = None
        self.root.after(80, self._drain)

    def _drain(self):
        try:
            while True:
                text = self._q.get_nowait()
                self._show(text)
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def _show(self, text: str):
        self.label.config(text=text)
        self.root.deiconify()
        if self._hide_job:
            try:
                self.root.after_cancel(self._hide_job)
            except Exception:
                pass
        self._hide_job = self.root.after(self.ttl_ms, self.root.withdraw)

    def push(self, text: str):
        """线程安全：任何线程都可调用。"""
        self._q.put(text)

    def run(self):
        self.root.mainloop()


def try_start_overlay(cfg) -> SubtitleOverlay | None:
    """在独立线程启动覆盖层；不可用返回 None。"""
    if not cfg.overlay:
        return None
    holder: dict = {}

    def _boot():
        try:
            ov = SubtitleOverlay(cfg.overlay_height, cfg.overlay_font, cfg.subtitle_ttl)
            holder["ov"] = ov
            ov.run()
        except Exception as e:
            holder["err"] = e

    t = threading.Thread(target=_boot, daemon=True)
    t.start()
    t.join(timeout=1.2)  # 等窗口初始化（mainloop 会一直阻塞，这里只等初始)
    if "ov" in holder:
        log.info("字幕覆盖层已就绪")
        return holder["ov"]
    if "err" in holder:
        log.warning("覆盖层启动失败：%s（流水线继续运行）", holder["err"])
    return None
