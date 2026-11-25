"""
一键启动：中继服务 + PC 流水线 + 手机端静态服务，终端打印局域网地址和二维码。

    python -m pc.launch              # 正常启动
    python -m pc.launch --demo       # 用内置样例跑通链路（不截图）
    python -m pc.launch --no-overlay # 不显示 PC 字幕条
"""
from __future__ import annotations

import argparse
import asyncio
import functools
import logging
import os
import socket
import sys
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from pc.config import Config, get_lan_ip          # noqa: E402
from pc.pipeline import Pipeline                   # noqa: E402
from pc.overlay import try_start_overlay           # noqa: E402
from relay.server import serve as relay_serve       # noqa: E402


def _banner(cfg: Config):
    ip = get_lan_ip()
    line = "=" * 56
    print("\n" + line)
    print("  游戏聊天实时翻译  ·  局域网模式")
    print(line)
    print(f"  配对码      : {cfg.pair}")
    print(f"  翻译引擎    : {cfg.translator}   目标语言: {cfg.target_lang}")
    print(f"  OCR 来源    : {cfg.ocr_source}   区域: {cfg.region}")
    print(f"  中继地址    : ws://{ip}:{cfg.relay_port}")
    print(f"  手机端地址  : http://{ip}:{cfg.phone_port}/")
    print(line)
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(cfg.phone_url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
        print("  手机扫码直接打开（需与电脑同一 WiFi）")
    except Exception:
        print("  手机访问上面的地址，参数已自动带上")
    print(line)
    print("  Ctrl+C 退出")
    print(line + "\n")


def _free_port(start: int, tries: int = 20) -> int:
    """端口被占用时自动向后找一个可用端口。"""
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("0.0.0.0", p))
                return p
            except OSError:
                continue
    return start


def _start_phone_server(cfg: Config):
    phone_dir = os.path.join(ROOT, "phone")
    handler = functools.partial(SimpleHTTPRequestHandler, directory=phone_dir)
    handler.log_message = lambda *a, **k: None  # 静音访问日志

    class Server(ThreadingHTTPServer):
        allow_reuse_address = True

    srv = Server(("0.0.0.0", cfg.phone_port), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


async def _amain(cfg: Config, overlay):
    pipe = Pipeline(cfg, overlay=overlay)
    relay_task = asyncio.create_task(
        relay_serve(host=cfg.relay_host, port=cfg.relay_port)
    )
    await asyncio.sleep(0.5)  # 让中继先绑定端口
    try:
        await pipe.run()
    finally:
        relay_task.cancel()


def main():
    ap = argparse.ArgumentParser(description="游戏聊天实时翻译（局域网）")
    ap.add_argument("--demo", action="store_true", help="使用内置样例，不截图 OCR")
    ap.add_argument("--no-overlay", action="store_true", help="不显示 PC 字幕条")
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )

    cfg = Config.load(args.config)
    cfg.ensure_pair()
    if args.demo:
        cfg.ocr_source = "demo"
    if args.no_overlay:
        cfg.overlay = False

    # 先定端口（占用自动顺延），再生成配置和二维码，保证印出来的地址可用
    cfg.relay_port = _free_port(cfg.relay_port)
    cfg.phone_port = _free_port(cfg.phone_port)
    cfg.save(args.config)

    _start_phone_server(cfg)
    overlay = try_start_overlay(cfg)
    _banner(cfg)

    try:
        asyncio.run(_amain(cfg, overlay))
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        if overlay:
            try:
                overlay.root.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
