@echo off
chcp 65001 >nul
title 打包游戏字幕翻译（生成单文件安装程序）
cd /d "%~dp0"

echo ============================================
echo   1/3 安装运行依赖与 PyInstaller
echo ============================================
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python 3.9+，请先安装并勾选 Add to PATH
    pause & exit /b 1
)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 ( echo [错误] 依赖安装失败 & pause & exit /b 1 )

echo.
echo ============================================
echo   2/3 PyInstaller 打包（onedir）
echo ============================================
python -m PyInstaller GameTranslator.spec --noconfirm
if errorlevel 1 ( echo [错误] PyInstaller 打包失败 & pause & exit /b 1 )

echo.
echo ============================================
echo   3/3 Inno Setup 生成单文件安装程序
echo ============================================
where ISCC >nul 2>nul (
    ISCC installer.iss
    echo.
    echo 安装程序已生成：dist\GameTranslator-Setup-0.2.0.exe
) else (
    echo [提示] 未检测到 Inno Setup 6。
    echo 绿色版已在 dist\GameTranslator\ ，双击 GameTranslator.exe 即可运行。
    echo 要生成 .exe 安装程序，请安装 Inno Setup 6 后重新运行本脚本。
)

echo.
pause
