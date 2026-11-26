"""Lingua Studio 桌面入口：原生窗口（WebView2）+ Python 后端。"""
from __future__ import annotations

import ctypes
import os
import sys

# 让 HuggingFace 走国内镜像；关闭 Windows 符号链接警告
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import webview  # noqa: E402

from pc.api import APP_NAME, StudioAPI  # noqa: E402
from pc.paths import asset_path, data_dir, ui_path  # noqa: E402


def _set_app_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Rifei.LinguaStudio.1"
        )
    except Exception:
        pass


def main():
    _set_app_id()
    api = StudioAPI()
    cfg = api._runtime.cfg

    ui_file = ui_path("index.html")
    if not os.path.exists(ui_file):
        raise SystemExit(f"找不到界面文件：{ui_file}")

    icon = asset_path("appicon.ico")
    if not os.path.exists(icon):
        icon = None

    # 适配高 DPI：窗口不超过屏幕可用区域的 92%
    try:
        import mss
        with mss.mss() as sct:
            mon = sct.monitors[1]
            max_w = int(mon["width"] * 0.94)
            max_h = int(mon["height"] * 0.92)
        width = min(int(cfg.window_width), max_w)
        height = min(int(cfg.window_height), max_h)
    except Exception:
        width, height = int(cfg.window_width), int(cfg.window_height)

    print("[app] creating window", flush=True)
    window = webview.create_window(
        APP_NAME,
        url=ui_file,
        js_api=api,
        width=width,
        height=height,
        min_size=(1080, 700),
        frameless=True,
        easy_drag=False,
        shadow=True,
        resizable=True,
        background_color="#050507",
        text_select=True,
        zoomable=False,
        confirm_close=False,
    )
    api._window = window
    print(f"[app] window created {width}x{height}; starting webview", flush=True)

    def _after_start():
        import time
        time.sleep(2.2)
        try:
            raw = window.evaluate_js(r"""
            (() => {
              const app = document.querySelector('.app');
              const main = document.querySelector('.main');
              const view = document.querySelector('.viewport');
              const hero = document.querySelector('.hero');
              const stat = document.querySelector('.stat-grid');
              const h1 = document.querySelector('.hero-copy h1');
              const copy = document.querySelector('.hero-copy');
              const stage = document.querySelector('.hero-stage');
              const orb = document.querySelector('.orb-wrap');
              const lede = document.querySelector('.lede');
              const actions = document.querySelector('.hero-actions');
              const css = getComputedStyle(document.documentElement);
              return JSON.stringify({
                ready: document.readyState,
                innerWidth, innerHeight, dpr: devicePixelRatio,
                app: app ? [app.clientWidth, app.clientHeight] : null,
                main: main ? [main.clientWidth, main.clientHeight] : null,
                view: view ? [view.clientWidth, view.clientHeight, view.scrollWidth] : null,
                hero: hero ? [hero.clientWidth, hero.scrollWidth, getComputedStyle(hero).gridTemplateColumns] : null,
                stat: stat ? [stat.clientWidth, stat.scrollWidth, getComputedStyle(stat).gridTemplateColumns] : null,
                sidebar: css.getPropertyValue('--sidebar'),
                bodyScroll: [document.body.scrollWidth, document.body.scrollHeight],
                font: h1 ? getComputedStyle(h1).fontSize : null,
                copy: copy ? [copy.clientWidth, copy.scrollWidth] : null,
                stage: stage ? [stage.clientWidth, stage.scrollWidth] : null,
                orb: orb ? [orb.clientWidth, orb.scrollWidth, orb.getBoundingClientRect().left, orb.getBoundingClientRect().right] : null,
                h1: h1 ? [h1.clientWidth, h1.scrollWidth] : null,
                lede: lede ? [lede.clientWidth, lede.scrollWidth, getComputedStyle(lede).maxWidth] : null,
                actions: actions ? [actions.clientWidth, actions.scrollWidth] : null,
                booted: typeof S !== 'undefined' ? S.booted : 'no-S',
                api: !!(window.pywebview && window.pywebview.api),
                asrPill: document.querySelector('#asrModelPill')?.textContent,
                page: document.querySelector('.page.is-active')?.id
              });
            })()
            """)
            path = os.path.join(data_dir(), "ui-metrics.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(raw))
            print("[metrics]", raw, flush=True)
        except Exception as e:
            print("[metrics-error]", e, flush=True)

        # 仅在 LINGUA_DEV=1 时启用本机调试入口：写 data/ui-eval.js 即可执行并回写结果
        if os.environ.get("LINGUA_DEV") == "1":
            import threading, time as _time

            def _watch():
                cmd = os.path.join(data_dir(), "ui-eval.js")
                res = os.path.join(data_dir(), "ui-eval-result.txt")
                # 忽略启动前遗留的调试命令，避免旧窗口关闭指令把新窗口关掉
                try:
                    last = os.path.getmtime(cmd) if os.path.exists(cmd) else 0.0
                except Exception:
                    last = 0.0
                while True:
                    try:
                        if os.path.exists(cmd):
                            m = os.path.getmtime(cmd)
                            if m != last:
                                last = m
                                _time.sleep(0.12)
                                with open(cmd, "r", encoding="utf-8") as f:
                                    code = f.read()
                                try:
                                    out = window.evaluate_js(code)
                                    text = "OK " + str(out)
                                except Exception as e:  # noqa: BLE001
                                    text = "ERR " + repr(e)
                                with open(res, "w", encoding="utf-8") as f:
                                    f.write(text)
                                print("[dev-eval]", text[:400], flush=True)
                    except Exception as e:  # noqa: BLE001
                        print("[dev-watch]", e, flush=True)
                    _time.sleep(0.25)

            threading.Thread(target=_watch, daemon=True).start()
            print("[app] dev eval watcher enabled", flush=True)

    webview.start(
        debug=False,
        func=_after_start,
        private_mode=False,
        storage_path=os.path.join(data_dir(), "webview"),
        icon=icon,
    )
    print("[app] webview.start returned", flush=True)

    # 窗口关闭后同步收尾，释放端口与后台线程
    try:
        api._runtime.shutdown()
    except Exception:
        pass
    # 某些 WebView2 / pythonnet 线程在窗口销毁后仍会驻留；显式结束进程，
    # 避免用户关闭后留下占着 8780/8781 端口的幽灵后台。
    try:
        import time
        time.sleep(0.25)
    except Exception:
        pass
    os._exit(0)


if __name__ == "__main__":
    main()
