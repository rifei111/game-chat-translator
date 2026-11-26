"""暴露给前端（WebView）的 API。所有方法返回 JSON 可序列化对象。"""
from __future__ import annotations

import base64
import io
import json
import os
import platform
import sys
import time
import traceback
import webbrowser

from pc.config import ASR_MODELS, OCR_LANGS, TARGET_LANGS, get_lan_ip
from pc.paths import data_dir, model_dir, resource_path
from pc.runtime import Runtime

APP_NAME = "Lingua Studio"
APP_VERSION = "1.0.0"


def _err(e: Exception) -> dict:
    return {"ok": False, "error": str(e), "trace": traceback.format_exc(limit=4)}


def _jpeg_data_url(image, quality: int = 86) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _png_data_url(image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


class StudioAPI:
    def __init__(self):
        self._runtime = Runtime()
        self._window = None
        self._maximized = False

    # ---------------- 初始化 ----------------
    def bootstrap(self) -> dict:
        try:
            rt = self._runtime
            state = rt.state()
            with rt.lock:
                subs = list(rt.subs)[-36:]
                logs = list(rt.logs)[-90:]
                cfg = rt.cfg.public()
                sub_cursor = rt._sub_seq
                log_cursor = rt._log_seq
            devices = rt.asr_devices()
            models = rt.asr_models_state()
            try:
                import mss
                with mss.mss() as sct:
                    monitors = [dict(m) for m in sct.monitors]
            except Exception:
                monitors = []
            return {
                "ok": True,
                "state": state,
                "config": cfg,
                "subtitles": subs,
                "logs": logs,
                "sub_cursor": sub_cursor,
                "log_cursor": log_cursor,
                "devices": devices,
                "models": models,
                "phone": rt.phone_qr(),
                "app": self.app_info(),
                "constants": {
                    "ocr_langs": OCR_LANGS,
                    "asr_models": ASR_MODELS,
                    "target_langs": TARGET_LANGS,
                    "monitors": monitors,
                },
            }
        except Exception as e:
            return _err(e)

    def app_info(self) -> dict:
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "data_dir": data_dir(),
            "model_dir": model_dir(),
            "resource_dir": resource_path(),
            "webview": "Edge WebView2",
        }

    def get_state(self, since_sub: int = 0, since_log: int = 0) -> dict:
        try:
            return {"ok": True, **self._runtime.get_delta(int(since_sub or 0), int(since_log or 0))}
        except Exception as e:
            return _err(e)

    def get_levels(self) -> dict:
        return {"ok": True, **self._runtime.asr_levels()}

    # ---------------- 服务控制 ----------------
    def start_all(self) -> dict:
        try:
            return self._runtime.start()
        except Exception as e:
            return _err(e)

    def start_voice(self) -> dict:
        """语音页专用：启动中继/手机/字幕条，但不启用屏幕 OCR。"""
        try:
            return self._runtime.start(voice_only=True)
        except Exception as e:
            return _err(e)

    def stop_all(self) -> dict:
        try:
            return self._runtime.stop()
        except Exception as e:
            return _err(e)

    def toggle_all(self) -> dict:
        try:
            return self._runtime.toggle()
        except Exception as e:
            return _err(e)

    # ---------------- 配置 ----------------
    def save_config(self, patch: dict) -> dict:
        try:
            cfg = self._runtime.update_config(patch or {})
            return {"ok": True, "config": cfg, "phone": self._runtime.phone_qr()}
        except Exception as e:
            return _err(e)

    def apply_translator(self) -> dict:
        try:
            return self._runtime.apply_translator()
        except Exception as e:
            return _err(e)

    def apply_vision(self) -> dict:
        try:
            return self._runtime.apply_vision()
        except Exception as e:
            return _err(e)

    def test_translate(self, text: str) -> dict:
        try:
            from lid import detect
            from pc.translator import build_translator
            cfg = self._runtime.cfg
            translator = build_translator(cfg)
            result = detect(text or "", target=cfg.target_lang)
            t0 = time.time()
            translated = translator.translate(result["clean"], result["lang"], cfg.target_lang)
            return {
                "ok": True,
                "lang": result["lang"],
                "confidence": result["confidence"],
                "src": result["clean"],
                "trans": translated or result["clean"],
                "engine": getattr(translator, "name", "unknown"),
                "elapsed_ms": int((time.time() - t0) * 1000),
                "degraded": not bool(translated),
            }
        except Exception as e:
            return _err(e)

    def manual_translate(self, text: str) -> dict:
        try:
            return self._runtime.manual_translate(text)
        except Exception as e:
            return _err(e)

    # ---------------- 屏幕 / 区域 ----------------
    def _grab_monitor(self):
        import mss
        sct = mss.mss()
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        from PIL import Image
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        sct.close()
        return img, monitor

    def screen_capture(self, hide_window: bool = True) -> dict:
        """截取整个桌面（可先隐藏主窗口），供前端拖拽圈选。"""
        try:
            if hide_window and self._window:
                try:
                    self._window.hide()
                except Exception:
                    pass
                time.sleep(0.35)
            image, monitor = self._grab_monitor()
            if hide_window and self._window:
                try:
                    self._window.show()
                except Exception:
                    pass
            return {
                "ok": True,
                "image": _jpeg_data_url(image, 84),
                "width": image.width,
                "height": image.height,
                "left": int(monitor.get("left", 0)),
                "top": int(monitor.get("top", 0)),
                "monitor": {k: v for k, v in monitor.items() if k != "name"},
            }
        except Exception as e:
            return _err(e)

    def apply_region(self, x: int, y: int, w: int, h: int) -> dict:
        try:
            x, y, w, h = int(x), int(y), int(w), int(h)
            if w < 20 or h < 20:
                return {"ok": False, "error": "区域太小，请重新框选"}
            cfg = self._runtime.update_config({
                "region": [x, y, w, h],
                "ocr_source": "screen",
            })
            self._runtime.log(f"已更新聊天区域：{x},{y} · {w}×{h}", "ok")
            self._runtime.apply_vision()
            return {"ok": True, "config": cfg, "phone": self._runtime.phone_qr()}
        except Exception as e:
            return _err(e)

    def preview_region(self) -> dict:
        try:
            from pc.ocr import ScreenOcr
            cfg = self._runtime.cfg
            provider = ScreenOcr(cfg.region, cfg.ocr_lang, cfg.ocr_min_score, cfg.ocr_line_gap)
            provider.prepare()
            image = provider.grab()
            result = provider.recognize(image)
            return {
                "ok": True,
                "image": _jpeg_data_url(image, 90),
                "lines": result["lines"],
                "elapsed_ms": result["elapsed_ms"],
                "region": cfg.region,
                "lang": cfg.ocr_lang,
            }
        except Exception as e:
            return _err(e)

    def ocr_warmup(self, lang: str = "") -> dict:
        try:
            from pc.ocr import OCR_LANG_LABEL, ScreenOcr
            cfg = self._runtime.cfg
            if lang:
                self._runtime.update_config({"ocr_lang": lang})
            t0 = time.time()
            provider = ScreenOcr(cfg.region, cfg.ocr_lang, cfg.ocr_min_score, cfg.ocr_line_gap)
            provider.prepare()
            return {"ok": True, "lang": cfg.ocr_lang,
                    "label": OCR_LANG_LABEL.get(cfg.ocr_lang, cfg.ocr_lang),
                    "elapsed_ms": int((time.time() - t0) * 1000)}
        except Exception as e:
            return _err(e)

    # ---------------- 手机 / 二维码 ----------------
    def phone_qr(self) -> dict:
        try:
            return {"ok": True, **self._runtime.phone_qr()}
        except Exception as e:
            return _err(e)

    def open_phone_page(self) -> dict:
        try:
            webbrowser.open(self._runtime.cfg.phone_url)
            return {"ok": True}
        except Exception as e:
            return _err(e)

    def copy_text(self, text: str) -> dict:
        try:
            import pyperclip
            pyperclip.copy(text or "")
            return {"ok": True}
        except Exception as e:
            return _err(e)

    def send_clipboard(self, text: str) -> dict:
        try:
            return self._runtime.send_clipboard(text)
        except Exception as e:
            return _err(e)

    def overlay_test(self, text: str = "") -> dict:
        try:
            return self._runtime.test_overlay(text)
        except Exception as e:
            return _err(e)

    # ---------------- 语音 ----------------
    def asr_devices(self) -> dict:
        return self._runtime.asr_devices()

    def asr_models(self) -> dict:
        return {"ok": True, "models": self._runtime.asr_models_state()}

    def asr_prepare(self, model: str) -> dict:
        try:
            return self._runtime.asr_prepare(model)
        except Exception as e:
            return _err(e)

    def asr_start(self, device_id: str, model: str, language: str, chunk) -> dict:
        try:
            return self._runtime.asr_start(device_id, model, language, float(chunk or 5))
        except Exception as e:
            return _err(e)

    def asr_stop(self) -> dict:
        try:
            return self._runtime.asr_stop()
        except Exception as e:
            return _err(e)

    # ---------------- 其他 ----------------
    def clear_feed(self) -> dict:
        try:
            self._runtime.clear_feed()
            return {"ok": True}
        except Exception as e:
            return _err(e)

    def export_logs(self) -> dict:
        try:
            rt = self._runtime
            with rt.lock:
                logs = list(rt.logs)
            name = time.strftime("lingua-logs-%Y%m%d-%H%M%S.txt")
            path = os.path.join(data_dir(), name)
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"{APP_NAME} {APP_VERSION}\n")
                f.write(f"exported: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n")
                for item in logs:
                    ts = time.strftime("%H:%M:%S", time.localtime(item["ts"] / 1000))
                    f.write(f"[{ts}] {item['level'].upper():<6} {item['msg']}\n")
                f.write("\n状态：\n")
                f.write(json.dumps(rt.state(), ensure_ascii=False, indent=2))
            return {"ok": True, "path": path}
        except Exception as e:
            return _err(e)

    def open_data_folder(self) -> dict:
        try:
            os.startfile(data_dir())
            return {"ok": True, "path": data_dir()}
        except Exception as e:
            return _err(e)

    # ---------------- 窗口 ----------------
    def ui_metrics(self) -> dict:
        try:
            js = """
            (() => {
              const app = document.querySelector('.app');
              const main = document.querySelector('.main');
              const view = document.querySelector('.viewport');
              const hero = document.querySelector('.hero');
              const stat = document.querySelector('.stat-grid');
              const css = getComputedStyle(document.documentElement);
              return JSON.stringify({
                innerWidth, innerHeight, dpr: devicePixelRatio,
                app: app ? [app.clientWidth, app.clientHeight] : null,
                main: main ? [main.clientWidth, main.clientHeight] : null,
                view: view ? [view.clientWidth, view.clientHeight, view.scrollWidth] : null,
                hero: hero ? [hero.clientWidth, hero.scrollWidth] : null,
                stat: stat ? [stat.clientWidth, stat.scrollWidth, getComputedStyle(stat).gridTemplateColumns] : null,
                sidebar: css.getPropertyValue('--sidebar'),
                bodyScroll: [document.body.scrollWidth, document.body.scrollHeight],
                font: getComputedStyle(document.querySelector('.hero-copy h1')).fontSize
              });
            })()
            """
            raw = self._window.evaluate_js(js)
            return {"ok": True, "raw": raw}
        except Exception as e:
            return _err(e)

    def _hwnd(self):
        if not self._window:
            return None
        native = getattr(self._window, "native", None)
        for attr in ("Handle", "handle", "hwnd", "HWND"):
            try:
                value = getattr(native, attr)
                if callable(value):
                    value = value()
                if value:
                    return int(value)
            except Exception:
                continue
        try:
            import ctypes
            return int(ctypes.windll.user32.FindWindowW(None, self._window.title))
        except Exception:
            return None

    def window_minimize(self) -> dict:
        try:
            self._window.minimize()
            return {"ok": True}
        except Exception as e:
            return _err(e)

    def window_toggle_max(self) -> dict:
        try:
            if self._maximized:
                self._window.restore()
                self._maximized = False
            else:
                self._window.maximize()
                self._maximized = True
            return {"ok": True, "maximized": self._maximized}
        except Exception as e:
            return _err(e)

    def window_start_resize(self) -> dict:
        """把鼠标交给 Windows 原生边缘拖拽，缩放流畅无抖动。"""
        try:
            import ctypes
            hwnd = self._hwnd()
            if not hwnd:
                return {"ok": False, "error": "无法获取窗口句柄"}
            ctypes.windll.user32.ReleaseCapture()
            ctypes.windll.user32.SendMessageW(hwnd, 0x00A1, 17, 0)  # WM_NCLBUTTONDOWN / HTBOTTOMRIGHT
            return {"ok": True}
        except Exception as e:
            return _err(e)

    def window_resize(self, width, height) -> dict:
        try:
            self._window.resize(int(width), int(height))
            return {"ok": True}
        except Exception as e:
            return _err(e)

    def window_close(self) -> dict:
        try:
            self._runtime.stop()
        except Exception:
            pass
        try:
            self._window.destroy()
        except Exception as e:
            return _err(e)
        return {"ok": True}

