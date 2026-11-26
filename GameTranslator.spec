# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置（在 Windows 上执行）：
    python -m PyInstaller GameTranslator.spec --noconfirm

产物：dist/GameTranslator/（onedir，启动快），由 Inno Setup 打成单个安装程序。
"""
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.dirname(SPEC))

datas, binaries, hidden = [], [], []

# OCR 模型 / onnxruntime 原生库 / lingua 编译扩展，整包收集
for pkg in ["rapidocr_onnxruntime", "onnxruntime", "lingua"]:
    d, b, h = collect_all(pkg)  # collect_all -> (datas, binaries, hiddenimports)
    datas += d
    hidden += h
    binaries += b

hidden += collect_submodules("rapidocr_onnxruntime")

# 手机端网页资源随程序打包
datas += [(os.path.join(ROOT, "phone"), "phone")]

a = Analysis(
    [os.path.join(ROOT, "entry.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=[
        "argostranslate",   # 可选离线翻译，体积大；需要时单独安装
        "PyQt5", "PySide2", "matplotlib", "pandas", "scipy",
        "tkinter.test",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GameTranslator",
    debug=False,
    bootloader_ignore_signals=False,
    console=True,          # 保留控制台：展示局域网地址与二维码
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="GameTranslator",
)
