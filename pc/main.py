"""
无覆盖层 / 只跑流水线（调试用）：
    python -m pc.main             # 读 config.json
    python -m pc.main --demo      # 内置样例
"""
from __future__ import annotations

import argparse
import asyncio
import logging

from .config import Config
from .pipeline import Pipeline
from .overlay import try_start_overlay
from .paths import config_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--no-overlay", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%H:%M:%S")
    cfg = Config.load(config_path())
    cfg.ensure_pair()
    if args.demo:
        cfg.ocr_source = "demo"
    if args.no_overlay:
        cfg.overlay = False

    overlay = try_start_overlay(cfg)
    pipe = Pipeline(cfg, overlay=overlay)
    try:
        asyncio.run(pipe.run())
    except KeyboardInterrupt:
        print("已退出")


if __name__ == "__main__":
    main()
