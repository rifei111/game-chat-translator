"""Generate the Lingua Studio app icon without external assets."""
from __future__ import annotations

import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "appicon.ico")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
px = img.load()

# Rounded-square gradient: cyan top-left -> signature blue -> mint bottom-right.
r = int(S * 0.22)
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S)
        if t < 0.52:
            k = t / 0.52
            c = (
                int(90 + (10 - 90) * k),
                int(200 + (132 - 200) * k),
                int(250 + (255 - 250) * k),
            )
        else:
            k = (t - 0.52) / 0.48
            c = (
                int(10 + (48 - 10) * k),
                int(132 + (209 - 132) * k),
                int(255 + (88 - 255) * k),
            )
        px[x, y] = (*c, 255)

mask = Image.new("L", (S, S), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([0, 0, S - 1, S - 1], radius=r, fill=255)
img.putalpha(mask)

# Glassy top highlight.
sheen = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sd = ImageDraw.Draw(sheen)
sd.ellipse([-S * 0.35, -S * 0.6, S * 1.1, S * 0.42], fill=(255, 255, 255, 36))
img = Image.alpha_composite(img, sheen)
img.putalpha(mask)

d = ImageDraw.Draw(img)
# Chat bubble in the middle.
bw, bh = int(S * 0.58), int(S * 0.40)
bx, by = (S - bw) // 2, int(S * 0.24)
bubble_r = int(bh * 0.30)
d.rounded_rectangle([bx, by, bx + bw, by + bh], radius=bubble_r, fill=(255, 255, 255, 244))
# Tail.
tail = [(bx + int(bw * 0.20), by + bh - 8), (bx + int(bw * 0.34), by + bh - 8), (bx + int(bw * 0.27), by + bh + int(bh * 0.22))]
d.polygon(tail, fill=(255, 255, 255, 244))
# Translation lines.
line1_y = by + int(bh * 0.30)
line2_y = by + int(bh * 0.52)
d.rounded_rectangle([bx + int(bw * 0.10), line1_y, bx + int(bw * 0.66), line1_y + int(bh * 0.10)], radius=8, fill=(10, 132, 255, 235))
d.rounded_rectangle([bx + int(bw * 0.10), line2_y, bx + int(bw * 0.46), line2_y + int(bh * 0.10)], radius=8, fill=(10, 132, 255, 200))
# Mint status dot.
dot_r = int(bh * 0.10)
d.ellipse([bx + int(bw * 0.76), line1_y, bx + int(bw * 0.76) + dot_r * 2, line1_y + dot_r * 2], fill=(48, 209, 88, 255))
# Accent slash mark lower-right.
d.rounded_rectangle([int(S * 0.67), int(S * 0.18), int(S * 0.73), int(S * 0.82)], radius=18, fill=(255, 255, 255, 70))

sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
img.save(OUT, format="ICO", sizes=sizes)
print(OUT, os.path.getsize(OUT))
