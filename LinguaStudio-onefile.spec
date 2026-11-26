# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Lingua Studio — single-file Windows executable.

Build:
  ..\.venv-studio\Scripts\python.exe -m PyInstaller --noconfirm --clean \
      --distpath dist-onefile --workpath build-onefile LinguaStudio-onefile.spec
"""
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.dirname(os.path.abspath(SPEC)))

datas = [
    (os.path.join(ROOT, "ui"), "ui"),
    (os.path.join(ROOT, "phone"), "phone"),
    (os.path.join(ROOT, "assets"), "assets"),
]
binaries = []
hiddenimports = [
    "clr",
    "pythonnet",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    "Microsoft.Web.WebView2.Core",
    "Microsoft.Web.WebView2.WinForms",
    "soundcard.mediafoundation",
    "soundcard.coreaudio",
    "_cffi_backend",
    "pyperclip",
    "bottle",
    "websockets",
    "rapidocr_onnxruntime",
    "faster_whisper",
    "ctranslate2",
    "av",
    "huggingface_hub",
    "tokenizers",
]

for pkg in (
    "webview", "pythonnet", "rapidocr", "rapidocr_onnxruntime",
    "onnxruntime", "faster_whisper", "ctranslate2", "av",
    "soundcard", "PIL", "numpy", "mss", "websockets", "bottle",
):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LinguaStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, "assets", "appicon.ico"),
)
