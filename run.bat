@echo off
setlocal
cd /d "%~dp0"

rem Prefer the project's development venv (one level above the app folder).
set "PYW=%~dp0..\.venv-studio\Scripts\pythonw.exe"
if exist "%PYW%" goto launch

rem Fallbacks: a local .venv or pythonw on PATH.
if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw.exe"

:launch
start "" "%PYW%" "%~dp0app.py"
endlocal
