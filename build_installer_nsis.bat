@echo off
chcp 65001 >nul
REM ============================================================
REM  NSIS 打包（Inno Setup 不可用时的替代方案）
REM
REM  与 build_installer.bat 的差别：
REM    - 只用 NSIS，不需要 Inno Setup，也不需要管理员权限
REM    - 装到 %LOCALAPPDATA%\Programs\GameTranslator（per-user），
REM      这样首跑写 config.json 不会因为 Program Files 只读而失败
REM
REM  用法：
REM    1) python -m pip install -r requirements.txt pyinstaller
REM    2) python -m PyInstaller GameTranslator.spec --noconfirm
REM    3) build_installer_nsis.bat
REM
REM  需要已安装 NSIS 3.x（makensis.exe 在 PATH 里，或设置了 NSISDIR）
REM  产物：dist\GameTranslator-Setup-0.2.0.exe
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist "dist\GameTranslator\GameTranslator.exe" (
    echo [x] 未找到 dist\GameTranslator\GameTranslator.exe
    echo     请先执行: python -m PyInstaller GameTranslator.spec --noconfirm
    exit /b 1
)

if not exist "build_nsis\app.ico" (
    echo [x] 未找到 build_nsis\app.ico
    exit /b 1
)

set "MAKENSIS="
if exist "%NSISDIR%\makensis.exe" set "MAKENSIS=%NSISDIR%\makensis.exe"
if not defined MAKENSIS if exist "%ProgramFiles(x86)%\NSIS\makensis.exe" set "MAKENSIS=%ProgramFiles(x86)%\NSIS\makensis.exe"
if not defined MAKENSIS if exist "%ProgramFiles%\NSIS\makensis.exe" set "MAKENSIS=%ProgramFiles%\NSIS\makensis.exe"
if not defined MAKENSIS where makensis.exe >nul 2>nul && set "MAKENSIS=makensis.exe"

if not defined MAKENSIS (
    echo [x] 没找到 makensis.exe
    echo     安装 NSIS 3.x 后重试，或设置 NSISDIR 指向便携版目录
    exit /b 1
)

echo ==^> 使用编译器: %MAKENSIS%
"%MAKENSIS%" /V2 "build_nsis\installer.nsi"
if errorlevel 1 (
    echo [x] NSIS 编译失败
    exit /b 1
)

echo.
echo 完成: dist\GameTranslator-Setup-0.2.0.exe
exit /b 0