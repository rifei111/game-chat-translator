; Inno Setup 脚本：把 PyInstaller 产物打成单个 Windows 安装程序
; 编译：ISCC installer.iss（需先装 Inno Setup 6）
#define MyAppName "游戏字幕翻译"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Rifei"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\GameTranslator
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=GameTranslator-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\GameTranslator.exe

[Files]
Source: "dist\GameTranslator\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\GameTranslator.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\GameTranslator.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "在桌面创建快捷方式"; GroupDescription: "附加选项:"

[Run]
Filename: "{app}\GameTranslator.exe"; Description: "立即启动"; Flags: nowait postinstall skipifsilent
