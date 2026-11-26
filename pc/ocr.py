"""OCR 层：屏幕截图 + RapidOCR 多语种模型（按语言切换）。

默认使用 PP-OCRv6 多语模型（中/日/英/欧洲语言），韩语、西里尔、阿拉伯语
按需下载专用识别模型。模型只加载一次并在进程内复用。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Protocol

log = logging.getLogger("ocr")

OCR_LANG_LABEL = {
    "auto": "自动多语",
    "ch": "中文+英文",
    "japan": "日语",
    "korean": "韩语",
    "cyrillic": "西里尔",
    "latin": "欧洲语言",
    "arabic": "阿拉伯语",
}


class OcrProvider(Protocol):
    def read_lines(self) -> list[str]:
        ...


# ---------------- demo ----------------
class DemoSource:
    """内置多语种样例：无需游戏即可预览整条翻译链路。"""

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

    def prepare(self):
        return True


# ---------------- RapidOCR 多语种 ----------------
_ENGINE_CACHE: dict[tuple[str, float], object] = {}
_ENGINE_LOCK = threading.Lock()


def _build_engine(lang: str, min_score: float):
    from rapidocr import ModelType, OCRVersion, RapidOCR

    key = (lang, round(min_score, 2))
    with _ENGINE_LOCK:
        if key in _ENGINE_CACHE:
            return _ENGINE_CACHE[key]

        params = {"Global.text_score": 0.30}
        if lang in ("japan", "korean", "cyrillic", "latin", "arabic"):
            params.update({
                "Rec.ocr_version": OCRVersion.PPOCRV4,
                "Rec.lang_type": lang,
                "Rec.model_type": ModelType.MOBILE,
            })
        # auto / ch 使用包内 PP-OCRv6 多语模型
        log.info("加载 OCR 模型：%s", OCR_LANG_LABEL.get(lang, lang))
        engine = RapidOCR(params=params)
        _ENGINE_CACHE[key] = engine
        return engine


class ScreenOcr:
    def __init__(self, region, lang: str = "auto", min_score: float = 0.62,
                 line_gap: int = 14):
        self.region = list(region)
        self.lang = lang if lang in OCR_LANG_LABEL else "auto"
        self.min_score = float(min_score)
        self.line_gap = int(line_gap)
        self._engine = None
        self._sct = None
        self._lock = threading.Lock()

    def prepare(self):
        if self._engine is None:
            self._engine = _build_engine(self.lang, self.min_score)
        return True

    def _ensure_sct(self):
        if self._sct is None:
            import mss
            self._sct = mss.mss()

    def grab(self, region=None):
        self._ensure_sct()
        x, y, w, h = region or self.region
        w, h = max(1, int(w)), max(1, int(h))
        shot = self._sct.grab({"top": int(y), "left": int(x), "width": w, "height": h})
        from PIL import Image
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def recognize(self, image, min_score: float | None = None) -> dict:
        """对 PIL Image 识别，返回 merged lines + 原始框。"""
        if self._engine is None:
            self.prepare()
        import numpy as np
        bgr = np.array(image.convert("RGB"))[:, :, ::-1]
        t0 = time.time()
        res = self._engine(bgr)
        elapsed = round((time.time() - t0) * 1000)
        threshold = self.min_score if min_score is None else float(min_score)

        items = []
        if res is not None and getattr(res, "txts", None):
            boxes = res.boxes
            for i, (text, score) in enumerate(zip(res.txts, res.scores)):
                text = (text or "").strip()
                score = float(score)
                if not text or score < threshold:
                    continue
                box = boxes[i] if boxes is not None else None
                if box is None:
                    continue
                xs = [float(p[0]) for p in box]
                ys = [float(p[1]) for p in box]
                items.append({
                    "text": text,
                    "score": round(score, 3),
                    "top": min(ys),
                    "left": min(xs),
                    "box": [int(min(xs)), int(min(ys)),
                            int(max(xs) - min(xs)), int(max(ys) - min(ys))],
                })

        items.sort(key=lambda t: (t["top"], t["left"]))
        groups: list[dict] = []
        for item in items:
            if groups and abs(item["top"] - groups[-1]["top"]) <= self.line_gap:
                groups[-1]["parts"].append(item)
            else:
                groups.append({"top": item["top"], "parts": [item]})

        merged = []
        for group in groups:
            parts = sorted(group["parts"], key=lambda t: t["left"])
            text = " ".join(p["text"] for p in parts).strip()
            score = round(sum(p["score"] for p in parts) / len(parts), 3)
            box = [
                min(p["box"][0] for p in parts),
                min(p["box"][1] for p in parts),
                max(p["box"][0] + p["box"][2] for p in parts) - min(p["box"][0] for p in parts),
                max(p["box"][1] + p["box"][3] for p in parts) - min(p["box"][1] for p in parts),
            ]
            if text:
                merged.append({"text": text, "score": score, "box": box})

        return {
            "lines": merged,
            "items": [{k: v for k, v in it.items() if k not in ("top", "left")}
                      for it in items],
            "elapsed_ms": elapsed,
        }

    def read_lines(self) -> list[str]:
        with self._lock:
            try:
                image = self.grab()
            except Exception as e:
                log.warning("截图失败：%s", e)
                return []
            result = self.recognize(image)
            return [line["text"] for line in result["lines"]]


def build_ocr(cfg, on_status: Callable[[str], None] | None = None) -> OcrProvider:
    if cfg.ocr_source == "screen":
        ocr = ScreenOcr(cfg.region, cfg.ocr_lang, cfg.ocr_min_score, cfg.ocr_line_gap)
        if on_status:
            on_status(f"OCR 模型：{OCR_LANG_LABEL.get(cfg.ocr_lang, cfg.ocr_lang)}")
        try:
            ocr.prepare()
        except Exception as e:
            log.warning("OCR 初始化失败：%s", e)
            raise
        return ocr
    return DemoSource()
