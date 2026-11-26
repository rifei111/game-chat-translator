@echo off
setlocal
cd /d "%~dp0"
copy /b LinguaStudio-portable.zip.001 + LinguaStudio-portable.zip.002 + LinguaStudio-portable.zip.003 + LinguaStudio-portable.zip.004 + LinguaStudio-portable.zip.005 + LinguaStudio-portable.zip.006 + LinguaStudio-portable.zip.007 LinguaStudio-portable.zip
if errorlevel 1 (
  echo Merge failed.
  pause
  exit /b 1
)
echo Done: LinguaStudio-portable.zip
certutil -hashfile LinguaStudio-portable.zip SHA256
pause
