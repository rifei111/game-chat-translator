"""二维码生成：手机扫码直连局域网页面。"""
from __future__ import annotations

import base64
import io


_cache: dict[str, str] = {}


def qr_data_url(text: str) -> str:
    if text in _cache:
        return _cache[text]
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M,
                       box_size=9, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#101014", back_color="#ffffff").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    _cache[text] = url
    return url
