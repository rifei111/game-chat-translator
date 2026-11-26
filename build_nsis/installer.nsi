; ============================================================
;  GameTranslator (游戏字幕翻译) NSIS installer
;  per-user install, no admin required (config.json lives next to the exe)
; ============================================================
Unicode true

!include "MUI2.nsh"
!include "FileFunc.nsh"
!include "LogicLib.nsh"

!define APP_NAME        "游戏字幕翻译"
!define APP_ID          "GameTranslator"
!define APP_VERSION     "0.2.0"
!define APP_EXE         "GameTranslator.exe"
!define APP_PUBLISHER   "Rifei"
!define APP_URL         "https://github.com/rifei111/game-chat-translator"
!define UNINST_KEY      "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"
!define APP_REG_KEY     "Software\${APP_ID}"

Name "${APP_NAME} ${APP_VERSION}"
OutFile "..\dist\GameTranslator-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\${APP_ID}"
InstallDirRegKey HKCU "${APP_REG_KEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
BrandingText "${APP_NAME} ${APP_VERSION}"

!define MUI_ICON "app.ico"
!define MUI_UNICON "app.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_NOREBOOTSUPPORT

; ---------- pages ----------
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; ---------- languages ----------
!insertmacro MUI_LANGUAGE "SimpChinese"
!insertmacro MUI_LANGUAGE "English"

; ============================================================
;  SECTION: main program files
; ============================================================
Section "主程序 (必需)" SecCore
  SectionIn RO
  SetShellVarContext current

  ; ask the user to close a running instance first
  ${If} ${FileExists} "$INSTDIR\${APP_EXE}"
    FileOpen $0 "$INSTDIR\${APP_EXE}" a
    ${If} $0 == ""
      MessageBox MB_OK|MB_ICONSTOP "检测到 ${APP_NAME} 正在运行。$\r$\n请先关闭程序再继续安装。"
      Abort
    ${Else}
      FileClose $0
    ${EndIf}
  ${EndIf}

  SetOutPath "$INSTDIR"
  File /r "..\dist\GameTranslator\*"
  SetOutPath "$INSTDIR"
  File "app.ico"

  WriteRegStr HKCU "${APP_REG_KEY}" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${APP_REG_KEY}" "Version" "${APP_VERSION}"

  ; ---- start menu ----
  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\app.ico" 0
  CreateShortCut "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk" "$INSTDIR\Uninstall.exe"
SectionEnd

; ============================================================
;  SECTION: desktop shortcut (optional)
; ============================================================
Section /o "桌面快捷方式" SecDesktop
  SetShellVarContext current
  CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\app.ico" 0
SectionEnd

; ============================================================
;  SECTION: uninstaller + Add/Remove Programs entry
; ============================================================
Section -Post
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0

  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayName"     "${APP_NAME}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayVersion"  "${APP_VERSION}"
  WriteRegStr   HKCU "${UNINST_KEY}" "Publisher"       "${APP_PUBLISHER}"
  WriteRegStr   HKCU "${UNINST_KEY}" "URLInfoAbout"    "${APP_URL}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\app.ico"
  WriteRegStr   HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr   HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize"   "$0"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify"        1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair"        1
SectionEnd

; ============================================================
;  descriptions
; ============================================================
LangString DESC_SecCore    ${LANG_SIMPCHINESE} "游戏字幕翻译主程序、运行时依赖与卸载程序。"
LangString DESC_SecDesktop ${LANG_SIMPCHINESE} "在桌面上创建启动快捷方式。"
LangString DESC_SecCore    ${LANG_ENGLISH}    "Main program, runtime dependencies and uninstaller."
LangString DESC_SecDesktop ${LANG_ENGLISH}    "Create a shortcut on the desktop."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecCore}    $(DESC_SecCore)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ============================================================
;  init
; ============================================================
Function .onInit
  SetShellVarContext current
FunctionEnd

Function un.onInit
  SetShellVarContext current
FunctionEnd

; ============================================================
;  SECTION: uninstall
; ============================================================
Section "Uninstall"
  SetShellVarContext current

  ; refuse to delete while the app is still running
  ${If} ${FileExists} "$INSTDIR\${APP_EXE}"
    FileOpen $0 "$INSTDIR\${APP_EXE}" a
    ${If} $0 == ""
      MessageBox MB_OK|MB_ICONSTOP "检测到 ${APP_NAME} 正在运行。$\r$\n请先关闭程序再卸载。"
      Abort
    ${Else}
      FileClose $0
    ${EndIf}
  ${EndIf}

  Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
  Delete "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk"
  RMDir  "$SMPROGRAMS\${APP_NAME}"
  Delete "$DESKTOP\${APP_NAME}.lnk"

  RMDir /r "$INSTDIR"

  DeleteRegKey HKCU "${UNINST_KEY}"
  DeleteRegKey HKCU "${APP_REG_KEY}"
SectionEnd