"""中继联调：模拟 PC + 手机两端，验证字幕/剪贴板消息路由。"""
import asyncio
import json
import websockets

URL = "ws://127.0.0.1:8780"
PAIR = "TEST01"


async def client(role: str, send_queue: list, received: list):
    async with websockets.connect(URL) as ws:
        await ws.send(json.dumps({"type": "hello", "pair": PAIR, "role": role}))
        ack = json.loads(await ws.recv())
        print(f"[{role}] ack: {ack}")

        async def sender():
            await asyncio.sleep(1.2)  # 等两端都加入房间
            for msg in send_queue:
                await ws.send(json.dumps(msg, ensure_ascii=False))
                await asyncio.sleep(0.2)

        async def receiver():
            async for raw in ws:
                received.append(json.loads(raw))

        await asyncio.gather(sender(), receiver())


async def main():
    pc_sent = [
        {"type": "subtitle", "lang": "ja", "src": "おっす", "trans": "[ja→zh] 哟"},
        {"type": "clipboard", "text": "来自PC的剪贴板", "from": "pc"},
    ]
    phone_sent = [
        {"type": "clipboard", "text": "来自手机的剪贴板", "from": "phone"},
    ]
    pc_recv, phone_recv = [], []

    pc_task = asyncio.create_task(client("pc", pc_sent, pc_recv))
    await asyncio.sleep(0.3)
    phone_task = asyncio.create_task(client("phone", phone_sent, phone_recv))
    await asyncio.sleep(1.5)
    pc_task.cancel(); phone_task.cancel()

    print("\n手机端收到：")
    for m in phone_recv: print(" ", m)
    print("\nPC 端收到：")
    for m in pc_recv: print(" ", m)

    ok = any(m.get("type") == "subtitle" for m in phone_recv) \
        and any(m.get("text") == "来自PC的剪贴板" for m in phone_recv) \
        and any(m.get("text") == "来自手机的剪贴板" for m in pc_recv)
    print("\n路由校验:", "通过" if ok else "失败")


asyncio.run(main())
