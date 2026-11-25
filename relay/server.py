"""WebSocket 中继：PC 与手机配对、双向转发字幕/剪贴板。只转发，不落库。"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Dict, Set

import websockets
from websockets.asyncio.server import ServerConnection

log = logging.getLogger("relay")

rooms: Dict[str, Set[ServerConnection]] = {}
conns: Dict[ServerConnection, tuple[str, str]] = {}


def _join(pair: str, ws: ServerConnection, role: str):
    rooms.setdefault(pair, set()).add(ws)
    conns[ws] = (pair, role)


def _leave(ws: ServerConnection):
    info = conns.pop(ws, None)
    if not info:
        return
    pair, _ = info
    room = rooms.get(pair)
    if room:
        room.discard(ws)
        if not room:
            rooms.pop(pair, None)


async def _broadcast(pair: str, sender: ServerConnection, payload: dict):
    for peer in list(rooms.get(pair, ())):
        if peer is sender:
            continue
        try:
            await peer.send(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass


async def handle(ws: ServerConnection):
    pair = None
    role = "unknown"
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") in ("hello", "join"):
                pair = (msg.get("pair") or msg.get("code") or "").strip().upper()
                if not pair:
                    await ws.send(json.dumps({"type": "error", "msg": "pair required"}))
                    continue
                role = msg.get("role", "unknown")
                _join(pair, ws, role)
                await ws.send(json.dumps({
                    "type": "paired", "pair": pair, "peers": len(rooms[pair]),
                }, ensure_ascii=False))
                await _broadcast(pair, ws, {"type": "peer_joined", "role": role})
                log.info("加入 pair=%s role=%s 在线=%d", pair, role, len(rooms[pair]))
                continue

            if pair is None:
                await ws.send(json.dumps({"type": "error", "msg": "hello first"}))
                continue

            msg.setdefault("from", role)
            await _broadcast(pair, ws, msg)
    finally:
        if pair:
            await _broadcast(pair, ws, {"type": "peer_left", "role": role})
        _leave(ws)


async def serve(host: str = "0.0.0.0", port: int = 8780):
    async with websockets.serve(handle, host, port, max_size=2 ** 20):
        log.info("中继已启动 %s:%d", host, port)
        await asyncio.Future()


async def main(port: int = 8780):
    await serve(port=port)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 8780))
