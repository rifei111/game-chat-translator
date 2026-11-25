"""
OCR 层：真实屏幕截图 + RapidOCR 识别（多语种），无引擎时回落 demo 样例。

返回按视觉行合并后的文本列表（自上而下），供流水线做去重与语种识别。
"""
from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("ocr")


class OcrProvider(Protocol):
    def read_lines(self) -> list[str]:
        ...


# ---------------- demo ----------------
class DemoSource:
    """内置样例轮播：没有游戏/没装 OCR 时也能跑通整条链路。"""

    SAMPLES = [
        "[Ruki] gg ez lol",
        "Yamato: おっす、今日もランク行こうぜ！",
        "민준: 안녕하세요! 같이 게임 할 사람?",
        "Ivan: Привет, пойдём в рейд вечером?",
        "Lena: Wie geht es dir heute?",
        "Pierre: Salut, tu veux jouer ce soir ?",
        "Carlos: Hola, ¿alguien quiere jugar?",
        "João: Olá, alguém quer jogar junto?",
        "Sakura: このMAP苦手なんだよね",
        "지훈: 탑 갈 사람 있어?",
        "Sergey: Го на мид, быстро",
        "Anna: Kannst du mich heilen?",
        "Lucas: On défend la base, ok?",
        "Diego: Necesitamos un support",
        "Mateus: Vamos ganhar essa",
        "Kenji: ナイスショット！",
        "Hana: もう一回行こう",
        "Dmitri: Хорошая игра",
        "Tom: nice one mate",
        "Emma: can someone cover left?",
    ]

    def __init__(self):
        self._i = 0

    def read_lines(self) -> list[str]:
        line = self.SAMPLES[self._i % len(self.SAMPLES)]
        self._i += 1
        return [line]


# ---------------- 真实截图 OCR ----------------
class ScreenOcr:
    """mss 截图 + RapidOCR 识别，按 y 坐标合并成视觉行。"""

    def __init__(self, region, min_score: float = 0.62, line_gap: int = 14):
        self.region = list(region)
        self.min_score = min_score
        self.line_gap = line_gap
        self._sct = None
        self._engine = None

    def _ensure(self):
        """初始化 OCR 引擎（截图模块在真正截图时才初始化，便于无显示环境测试）。"""
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._engine = RapidOCR()

    def _ensure_sct(self):
        if self._sct is None:
            import mss
            self._sct = mss.mss()

    def grab(self):
        """截取圈选区域，返回 PIL Image（调试/预览用）。"""
        self._ensure_sct()
        x, y, w, h = self.region
        shot = self._sct.grab({"top": y, "left": x, "width": w, "height": h})
        from PIL import Image
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def read_lines(self) -> list[str]:
        self._ensure()
        import numpy as np
        try:
            img = np.array(self.grab())[:, :, ::-1]  # RGB -> BGR 给 RapidOCR
        except Exception as e:
            log.warning("截图失败（无显示/权限？）：%s", e)
            return []

        result, _ = self._engine(img)
        if not result:
            return []

        # result: [(box, text, score), ...]  box = 4 顶点
        items = []
        for box, text, score in result:
            if float(score) < self.min_score:
                continue
            text = (text or "").strip()
            if not text:
                continue
            top = min(p[1] for p in box)
            left = min(p[0] for p in box)
            items.append((top, left, text))

        # 按 y 聚成视觉行，行内按 x 拼接
        items.sort(key=lambda t: (t[0], t[1]))
        lines: list[list] = []
        for top, left, text in items:
            if lines and abs(top - lines[-1][0]) <= self.line_gap:
                lines[-1][1].append((left, text))
            else:
                lines.append([top, [(left, text)]])

        out = []
        for _, parts in lines:
            parts.sort(key=lambda p: p[0])
            out.append(" ".join(p[1] for p in parts))
        return out


def build_ocr(cfg) -> OcrProvider:
    if cfg.ocr_source == "screen":
        try:
            ocr = ScreenOcr(cfg.region, cfg.ocr_min_score, cfg.ocr_line_gap)
            ocr._ensure()  # 只预先加载 OCR 引擎，截图模块留到运行期
            log.info("OCR 引擎就绪：RapidOCR，区域 %s", cfg.region)
            return ocr
        except Exception as e:
            log.warning("OCR 初始化失败（%s），回落演示样例", e)
    return DemoSource()
