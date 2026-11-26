"""PC 置顶字幕条：Win32 分层窗口 + 每像素透明，圆角玻璃、鼠标穿透、滑入淡出。

不使用 tkinter：Tk 的透明窗口在本机运行时会触发原生断点异常。这里直接用
UpdateLayeredWindow 合成一张 RGBA 位图，层级、透明度和鼠标穿透都由 Win32 控制，
渲染使用 Pillow，视觉和动效稳定可控。
"""
from __future__ import annotations

import ctypes
import logging
import math
import queue
import sys
import threading
import time
from ctypes import wintypes

log = logging.getLogger("overlay")

_WM_TIMER = 0x0113
_WM_CLOSE = 0x0010
_WM_DESTROY = 0x0002
_WM_APP_PUSH = 0x0400 + 1
_WM_APP_QUIT = 0x0400 + 2

_TIMER_ANIM = 1
_TIMER_TTL = 2

_WS_POPUP = 0x80000000
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_TOOLWINDOW = 0x00000080
_WS_EX_TOPMOST = 0x00000008
_WS_EX_NOACTIVATE = 0x08000000

_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040
_HWND_TOPMOST = -1

_ULW_ALPHA = 0x00000002
_AC_SRC_OVER = 0x00
_AC_SRC_ALPHA = 0x01
_DIB_RGB_COLORS = 0
_BI_RGB = 0

_SW_SHOWNOACTIVATE = 4
_SW_HIDE = 0

_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


def _bind_win32():
    """显式声明 64 位参数类型，避免 LPARAM 被 ctypes 当成 32 位 int 溢出。"""
    if sys.platform != "win32":
        return
    u = ctypes.windll.user32
    g = ctypes.windll.gdi32
    u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.DefWindowProcW.restype = ctypes.c_ssize_t
    u.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    u.CreateWindowExW.restype = wintypes.HWND
    u.UpdateLayeredWindow.argtypes = [
        wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE),
        wintypes.HDC, ctypes.POINTER(wintypes.POINT), wintypes.DWORD,
        ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD,
    ]
    u.UpdateLayeredWindow.restype = wintypes.BOOL
    u.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    u.SetWindowPos.restype = wintypes.BOOL
    u.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
    u.SetTimer.restype = ctypes.c_size_t
    u.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
    u.KillTimer.restype = wintypes.BOOL
    u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u.ShowWindow.restype = wintypes.BOOL
    u.GetDC.argtypes = [wintypes.HWND]
    u.GetDC.restype = wintypes.HDC
    u.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    u.ReleaseDC.restype = ctypes.c_int
    u.GetSystemMetrics.argtypes = [ctypes.c_int]
    u.GetSystemMetrics.restype = ctypes.c_int
    u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.PostMessageW.restype = wintypes.BOOL
    u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    u.GetMessageW.restype = ctypes.c_int
    u.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u.DispatchMessageW.restype = ctypes.c_ssize_t
    u.DestroyWindow.argtypes = [wintypes.HWND]
    u.DestroyWindow.restype = wintypes.BOOL
    u.PostQuitMessage.argtypes = [ctypes.c_int]
    u.SetProcessDPIAware.argtypes = []
    u.SetProcessDPIAware.restype = wintypes.BOOL
    g.GetDeviceCaps.argtypes = [wintypes.HDC, ctypes.c_int]
    g.GetDeviceCaps.restype = ctypes.c_int
    g.CreateCompatibleDC.argtypes = [wintypes.HDC]
    g.CreateCompatibleDC.restype = wintypes.HDC
    g.DeleteDC.argtypes = [wintypes.HDC]
    g.DeleteDC.restype = wintypes.BOOL
    g.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    g.SelectObject.restype = wintypes.HGDIOBJ
    g.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    g.DeleteObject.restype = wintypes.BOOL
    g.CreateDIBSection.argtypes = [
        wintypes.HDC, ctypes.POINTER(_BITMAPINFO), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
    ]
    g.CreateDIBSection.restype = wintypes.HBITMAP


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


if sys.platform == "win32":
    _bind_win32()


def _font(size: int, bold: bool = False, chinese: bool = False) -> "ImageFont.FreeTypeFont":
    from PIL import ImageFont
    candidates = []
    if chinese:
        candidates = [
            (r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc"),
            r"C:\Windows\Fonts\msyh.ttf",
        ]
    candidates += [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


class SubtitleOverlay:
    """线程安全的置顶字幕条。push() 可以在任意线程调用。"""

    def __init__(self, height: int = 118, font_size: int = 23, ttl: float = 8.0,
                 opacity: float = 0.88, radius: int = 26):
        self.ttl_ms = max(1200, int(ttl * 1000))
        self.target_alpha = max(0.30, min(1.0, float(opacity)))
        self.req_height = max(64, int(height))
        self.req_font = max(14, int(font_size))
        self.radius = max(8, min(40, int(radius)))
        self._q: queue.Queue = queue.Queue()
        self.hwnd = 0
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._dead = False
        self._wndproc_ref = None
        self._cls_name = f"LinguaSubOverlay_{id(self)}"
        self.width = 0
        self.height = 0
        self._x = self._y = 0
        self._img = None
        self._alpha = 0.0
        self._target_alpha = 0.0
        self._hide_after = False
        self._animating = False
        self._last_error = ""
        self._text = ""
        self._meta = ""

    # ---------------- 生命周期 ----------------
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="subtitle-overlay")
        self._thread.start()
        self._ready.wait(timeout=2.0)
        if not self.hwnd:
            raise RuntimeError(self._last_error or "字幕条窗口创建失败")

    def shutdown(self):
        self._dead = True
        if self.hwnd:
            try:
                # 只投递一次 WM_CLOSE：窗口线程销毁窗口并退出消息循环。
                # 避免 DestroyWindow 与 WM_APP_QUIT 重复销毁造成原生断点。
                ctypes.windll.user32.PostMessageW(self.hwnd, _WM_CLOSE, 0, 0)
            except Exception:
                pass
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)

    # ---------------- 对外 ----------------
    def push(self, text: str, meta: str = "LINGUA · 实时翻译"):
        if text and not self._dead:
            self._q.put((str(text), str(meta)))
            self._post(_WM_APP_PUSH, 0, 0)

    def _post(self, msg, wp, lp):
        if self.hwnd:
            ctypes.windll.user32.PostMessageW(self.hwnd, msg, wp, lp)

    # ---------------- Win32 ----------------
    def _run(self):
        try:
            self._create_window()
            self._ready.set()
            self._message_loop()
        except Exception as e:
            self._last_error = str(e)
            log.warning("字幕条线程异常：%s", e)
            self._ready.set()

    def _create_window(self):
        from PIL import Image, ImageDraw, ImageFilter

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        gdi32 = ctypes.windll.gdi32

        user32.SetProcessDPIAware()
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        dpi = 96.0
        try:
            hdc = user32.GetDC(0)
            dpi = gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            user32.ReleaseDC(0, hdc)
        except Exception:
            pass
        scale = max(1.0, dpi / 96.0)

        self.width = min(int(sw * 0.78), int(1420 * scale))
        self.height = int(self.req_height * scale)
        self.width = max(760, self.width)
        self.height = max(76, self.height)
        self.radius_px = int(self.radius * scale)
        self.font_px = max(16, int(self.req_font * scale))
        self.meta_px = max(10, int(11 * scale))
        self.pad = int(40 * scale)
        self._x = max(0, (sw - self.width) // 2)
        self._y = max(0, sh - self.height - int(64 * scale))

        hInstance = kernel32.GetModuleHandleW(None)
        self._wndproc_ref = _WNDPROC(self._wndproc)
        wc = _WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
        wc.style = 0x0002 | 0x0001  # CS_HREDRAW | CS_VREDRAW
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hInstance
        wc.hCursor = 0
        wc.hbrBackground = 0
        wc.lpszClassName = self._cls_name
        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            err = ctypes.get_last_error()
            if err not in (0, 1410):  # 1410 = class already exists
                self._last_error = f"RegisterClassExW 失败：{err}"
                return

        ex = (_WS_EX_LAYERED | _WS_EX_TRANSPARENT | _WS_EX_TOOLWINDOW |
              _WS_EX_TOPMOST | _WS_EX_NOACTIVATE)
        self.hwnd = user32.CreateWindowExW(
            ex, self._cls_name, "Lingua Subtitle",
            _WS_POPUP, self._x, self._y, self.width, self.height,
            0, 0, hInstance, None,
        )
        if not self.hwnd:
            self._last_error = f"CreateWindowExW 失败：{ctypes.get_last_error()}"
            return

        user32.ShowWindow(self.hwnd, _SW_HIDE)
        log.info("字幕条窗口已就绪：%sx%s @ %s,%s", self.width, self.height, self._x, self._y)

    def _message_loop(self):
        user32 = ctypes.windll.user32
        msg = wintypes.MSG()
        while not self._dead and user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == _WM_APP_PUSH:
                self._consume()
                return 0
            if msg == _WM_TIMER:
                if wparam == _TIMER_ANIM:
                    self._tick()
                elif wparam == _TIMER_TTL:
                    self._begin_hide()
                return 0
            if msg == _WM_CLOSE:
                ctypes.windll.user32.DestroyWindow(hwnd)
                return 0
            if msg == _WM_DESTROY:
                ctypes.windll.user32.KillTimer(hwnd, _TIMER_ANIM)
                ctypes.windll.user32.KillTimer(hwnd, _TIMER_TTL)
                ctypes.windll.user32.PostQuitMessage(0)
                return 0
            if msg == _WM_APP_QUIT:
                ctypes.windll.user32.DestroyWindow(hwnd)
                return 0
        except Exception as e:
            log.warning("字幕条消息异常：%s", e)
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _consume(self):
        try:
            text, meta = self._q.get_nowait()
        except queue.Empty:
            return
        self._render(text, meta)
        self._show()

    def _base_image(self, text: str, meta: str):
        from PIL import Image, ImageDraw, ImageFilter, ImageFont

        S = 2  # 超采样倍率
        w, h = self.width, self.height
        W, H = w * S, h * S
        r = self.radius_px * S
        pad = self.pad * S

        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

        # 柔和外阴影：模拟 Apple 的悬浮层
        shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.rounded_rectangle([pad // 2, 10 * S, W - 2, H - 2], radius=r,
                             fill=(0, 0, 0, 95))
        shadow = shadow.filter(ImageFilter.GaussianBlur(16 * S))
        canvas.alpha_composite(shadow)

        # 玻璃主体（深空黑 + 轻微冷色）
        body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(body)
        bd.rounded_rectangle([2, 2, W - 2, H - 2], radius=r,
                             fill=(17, 18, 24, 232), outline=(255, 255, 255, 30),
                             width=max(1, S))
        # 顶部高光与底部内阴影
        bd.rounded_rectangle([2, 2, W - 2, 12 * S], radius=r,
                             fill=(255, 255, 255, 6))
        bd.line([pad // 2, H - 2, W - pad // 2, H - 2], fill=(0, 0, 0, 70), width=S)
        # 左侧蓝色强调条
        bd.rounded_rectangle([24 * S, 24 * S, 30 * S, H - 24 * S], radius=3 * S,
                             fill=(10, 132, 255, 255))
        canvas.alpha_composite(body)

        # 文本
        d = ImageDraw.Draw(canvas)
        meta_font = _font(self.meta_px * S, False, True)
        text_font = _font(self.font_px * S, True, True)
        meta_text = (meta or "").upper()
        if meta_text:
            d.text((pad + 22 * S, 18 * S), meta_text, font=meta_font,
                   fill=(160, 160, 172, 235))

        # 右上角品牌小字
        brand = "LINGUA STUDIO"
        bbox = d.textbbox((0, 0), brand, font=meta_font)
        d.text((W - pad - (bbox[2] - bbox[0]), 18 * S), brand, font=meta_font,
               fill=(130, 150, 175, 190))

        # 自动换行：最多两行，超出省略
        max_w = W - (pad + 32 * S) * 2
        lines = []
        cur = ""
        for ch in text or "":
            trial = cur + ch
            if d.textlength(trial, font=text_font) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = ch
                if len(lines) >= 2:
                    break
        if cur and len(lines) < 2:
            lines.append(cur)
        if len(lines) == 2:
            rest = text[len("".join(lines)):]
            if rest:
                while lines[1] and d.textlength(lines[1] + "…", font=text_font) > max_w:
                    lines[1] = lines[1][:-1]
                lines[1] += "…"

        line_h = int(self.font_px * 1.24 * S)
        total_h = line_h * len(lines)
        start_y = int(H * 0.60) - total_h // 2 + line_h // 2
        for i, line in enumerate(lines):
            bbox = d.textbbox((0, 0), line, font=text_font)
            lw = bbox[2] - bbox[0]
            x = W // 2 - lw // 2 - bbox[0]
            d.text((x, start_y + i * line_h), line, font=text_font,
                   fill=(245, 245, 247, 255), anchor="lm")
        return canvas.resize((w, h), Image.LANCZOS)

    def _render(self, text: str, meta: str):
        self._text, self._meta = text, meta
        try:
            self._img = self._base_image(text, meta)
        except Exception as e:
            log.warning("字幕条绘制失败：%s", e)
            self._img = None

    def _show(self):
        user32 = ctypes.windll.user32
        if not self.hwnd or self._img is None:
            return
        user32.KillTimer(self.hwnd, _TIMER_TTL)
        user32.SetTimer(self.hwnd, _TIMER_TTL, self.ttl_ms, None)
        self._hide_after = False
        self._target_alpha = self.target_alpha
        if self._alpha < 0.01:
            self._alpha = 0.18
            self._slide = 14 * max(1, int(self.height / 118))
        self._target_y = self._y
        user32.ShowWindow(self.hwnd, _SW_SHOWNOACTIVATE)
        user32.SetWindowPos(self.hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
                            _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW)
        self._animating = True
        user32.SetTimer(self.hwnd, _TIMER_ANIM, 15, None)
        self._tick(force=True)

    def _begin_hide(self):
        self._target_alpha = 0.0
        self._hide_after = True
        self._animating = True
        ctypes.windll.user32.SetTimer(self.hwnd, _TIMER_ANIM, 15, None)

    def _tick(self, force: bool = False):
        from PIL import Image
        user32 = ctypes.windll.user32
        if not self.hwnd or self._img is None:
            return
        target = 0.0 if self._hide_after else self.target_alpha
        self._alpha += (target - self._alpha) * 0.22
        if abs(target - self._alpha) < 0.012:
            self._alpha = target
            if self._hide_after:
                self._animating = False
                user32.KillTimer(self.hwnd, _TIMER_ANIM)
                user32.ShowWindow(self.hwnd, _SW_HIDE)
                self._hide_after = False
                return
            self._animating = False
            user32.KillTimer(self.hwnd, _TIMER_ANIM)
        img = self._img
        # 逐像素 alpha + 预乘（numpy 向量化，避免每帧 Python 像素循环）
        try:
            import numpy as np
            arr = np.array(img, dtype=np.float32)
            a = arr[:, :, 3] * self._alpha
            arr[:, :, 0] *= a / 255.0
            arr[:, :, 1] *= a / 255.0
            arr[:, :, 2] *= a / 255.0
            arr[:, :, 3] = a
            out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")
        except Exception:
            out = img
        self._blit(out)
        self._slide *= 0.72
        if self._slide < 0.6:
            self._slide = 0.0
        if force:
            self._animating = True

    def _blit(self, image):
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        w, h = image.size
        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = _BI_RGB
        bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bmi), _DIB_RGB_COLORS,
                                      ctypes.byref(bits), None, 0)
        old = gdi32.SelectObject(hdc_mem, hbmp)
        data = image.tobytes("raw", "BGRA")
        ctypes.memmove(bits, data, len(data))
        size = wintypes.SIZE(w, h)
        src = wintypes.POINT(0, 0)
        slide = int(round(getattr(self, "_slide", 0) or 0))
        dst = wintypes.POINT(int(self._x), int(self._y - slide))
        blend = _BLENDFUNCTION(_AC_SRC_OVER, 0, 255, _AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(self.hwnd, hdc_screen, ctypes.byref(dst),
                                   ctypes.byref(size), hdc_mem, ctypes.byref(src),
                                   0, ctypes.byref(blend), _ULW_ALPHA)
        gdi32.SelectObject(hdc_mem, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)


def try_start_overlay(cfg) -> SubtitleOverlay | None:
    if not cfg.overlay:
        return None
    try:
        ov = SubtitleOverlay(cfg.overlay_height, cfg.overlay_font,
                             cfg.subtitle_ttl, cfg.overlay_opacity, cfg.overlay_radius)
        ov.start()
        log.info("字幕条已就绪")
        return ov
    except Exception as e:
        log.warning("字幕条启动失败：%s", e)
        return None
