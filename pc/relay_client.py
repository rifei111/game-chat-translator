"""PC 端到中继的 WebSocket 客户端：自动重连、注册配对、消息回调。"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Optional

import websockets

log = logging.getLogger("relay-client")


class RelayClient:
    def __init__(self, url: str, pair: str, role: str,
                 on_message: Callable[[dict], None]):
        self.url = url
        self.pair = pair
        self.role = role
        self.on_message = on_message
        self._ws: Optional[websockets.asyncio.client.ClientConnection] = None
        self._stop = False

    async def send(self, msg: dict):
        if not self._ws:
            return
        try:
            await self._ws.send(json.dumps(msg, ensure_ascii=False))
        except Exception:
            self._ws = None

    async def run(self):
        backoff = 1
        while not self._stop:
            try:
                async with websockets.connect(self.url) as ws:
                    self._ws = ws
                    await ws.send(json.dumps({
                        "type": "hello", "pair": self.pair, "role": self.role,
                    }, ensure_ascii=False))
                    backoff = 1
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        self.on_message(msg)
            except Exception as e:
                log.warning("relay disconnected: %s", e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)

    def stop(self):
        self._stop = True
