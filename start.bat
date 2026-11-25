@echo off
chcp 65001 >nul
title 游戏字幕翻译
cd /d "%~dp0"

rem 首次运行会生成 config.json，之后改这个文件即可
python -m pc.launch

if errorlevel 1 (
    echo.
    echo 启动失败。若提示缺少依赖，请先运行 install.bat
    pause
)
