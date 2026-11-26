import sys, time
sys.path.insert(0, r'C:\Users\23151\Doubao\chats\2026-11-26\new-chat\LinguaStudio')
from pc.overlay import SubtitleOverlay
ov = SubtitleOverlay(height=118, font_size=23, ttl=8.0, opacity=0.88, radius=26)
ov.start()
print('hwnd', ov.hwnd, 'size', ov.width, ov.height)
ov.push('今天也去打排位吧。别再单走了，等我开团。', 'JA → 简体中文 · 实时翻译')
time.sleep(2.5)
print('visible after push')
time.sleep(1)
ov.shutdown()
time.sleep(0.5)
print('done')
