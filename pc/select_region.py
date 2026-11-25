"""
圈选 OCR 区域：全屏半透明窗口，鼠标拖出一个矩形，回车确认写入 config.json。

    python -m pc.select_region
"""
from __future__ import annotations

import logging

from .config import Config

log = logging.getLogger("region")


def pick(cfg: Config):
    import tkinter as tk

    root = tk.Tk()
    root.attributes("-fullscreen", True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.35)
    root.configure(bg="black")
    root.config(cursor="crosshair")

    canvas = tk.Canvas(root, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    hint = canvas.create_text(
        root.winfo_screenwidth() // 2, 40,
        text="拖拽框选游戏聊天区域，回车确认，Esc 取消  ·  Esc / Enter",
        fill="white", font=("Microsoft YaHei", 16),
    )

    state = {"x0": 0, "y0": 0, "rect": None, "box": None}

    def on_press(e):
        state["x0"], state["y0"] = e.x, e.y
        if state["rect"]:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="#e94560", width=3)

    def on_drag(e):
        if state["rect"]:
            canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

    def on_release(e):
        x1, y1 = min(state["x0"], e.x), min(state["y0"], e.y)
        x2, y2 = max(state["x0"], e.x), max(state["y0"], e.y)
        if x2 - x1 < 20 or y2 - y1 < 20:
            state["box"] = None
            return
        state["box"] = [int(x1), int(y1), int(x2 - x1), int(y2 - y1)]

    def confirm(_=None):
        if state["box"]:
            cfg.region = state["box"]
            cfg.ocr_source = "screen"
            cfg.save()
            print(f"已保存区域：{cfg.region}  -> config.json")
        else:
            print("没有选中有效区域，未保存")
        root.destroy()

    def cancel(_=None):
        print("已取消")
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Return>", confirm)
    root.bind("<Escape>", cancel)

    root.mainloop()


def main():
    cfg = Config.load()
    try:
        pick(cfg)
    except Exception as e:
        print("无法打开图形选区窗口：", e)
        print("可手动改 config.json 里的 region: [x, y, w, h]")


if __name__ == "__main__":
    main()
