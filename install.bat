@echo off
chcp 65001 >nul
title 游戏字幕翻译 - 安装依赖
cd /d "%~dp0"

echo ============================================
echo   安装依赖（首次运行，需要联网）
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 没有检测到 python，请先安装 Python 3.9+ 并勾选 Add to PATH
    pause
    exit /b 1
)

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo 安装完成。双击 start.bat 启动。
pause
