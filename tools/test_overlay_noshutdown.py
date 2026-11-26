import sys, time
sys.path.insert(0, r'C:\Users\23151\Doubao\chats\2026-11-26\new-chat\LinguaStudio')
from pc.overlay import SubtitleOverlay
ov = SubtitleOverlay(height=118, font_size=23, ttl=20.0, opacity=0.88, radius=26)
ov.start()
print('hwnd', ov.hwnd, 'size', ov.width, ov.height, flush=True)
ov.push('字幕条无关闭测试：进程退出后窗口应随进程消失。', 'TEST · WIN32 OVERLAY')
time.sleep(4)
print('main exit without shutdown', flush=True)
