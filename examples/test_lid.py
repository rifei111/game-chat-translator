"""语种识别自检：跑一批外服聊天样例，打印判定结果。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lid import detect

SAMPLES = [
    "[Rifei] gg ez lol",
    "Yamato: おっす、今日もランク行こうぜ！",
    "민준: 안녕하세요! 같이 게임 할 사람?",
    "Ivan: Привет, пойдём в рейд вечером?",
    "Lena: Wie geht es dir heute? Lust auf eine Runde?",
    "Pierre: Salut, tu veux jouer ce soir ?",
    "Carlos: Hola, ¿alguien quiere jugar una partida?",
    "João: Olá, alguém quer jogar junto?",
    "Mehmet: Merhaba, akşam oynamak isteyen var mı?",
    "Omar: مرحبا، هل يريد أحد اللعب الليلة؟",
    "小明: 这把我来打野，大家跟我节奏",
    "akira: よろしく",
    "xX_Shadow_Xx: 123123",
    "???",
    "[Bot] Welcome to the server!",
]

print(f"{'原文':<45} {'语种':<8} {'置信度':<7} {'需翻译'}")
print("-" * 80)
for s in SAMPLES:
    r = detect(s)
    print(f"{s:<45} {r['lang']:<8} {r['confidence']:<7} {r['need_translate']}")
