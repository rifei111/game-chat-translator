@echo off
chcp 65001 >nul
title 圈选游戏聊天区域
cd /d "%~dp0"
python -m pc.select_region
pause
