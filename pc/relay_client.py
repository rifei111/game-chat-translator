"""PC 到中继的 WebSocket 客户端：自动重连、注册配对、消息回调。"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

from websockets.asyncio.client import ClientConnection, connect

log = logging.getLogger("relay-client")


class RelayClient:
    def __init__(self, url: str, pair: str, role: str,
                 on_message: Callable[[dict], None]):
        self.url = url
        self.pair = pair
        self.role = role
        self.on_message = on_message
        self._ws: Optional[ClientConnection] = None
        self._stop = False

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def send(self, msg: dict):
        ws = self._ws
        if not ws:
            return
        try:
            await ws.send(json.dumps(msg, ensure_ascii=False))
        except Exception:
            self._ws = None

    async def run(self):
        backoff = 1
        while not self._stop:
            try:
                async with connect(self.url) as ws:
                    self._ws = ws
                    await ws.send(json.dumps({
                        "type": "hello", "pair": self.pair, "role": self.role,
                    }, ensure_ascii=False))
                    backoff = 1
                    log.info("中继已连接 %s", self.url)
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        try:
                            self.on_message(msg)
                        except Exception as e:
                            log.warning("处理中继消息失败：%s", e)
            except Exception as e:
                if self._stop:
                    break
                log.warning("relay disconnected: %s", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)
            finally:
                self._ws = None

    def stop(self):
        self._stop = True
