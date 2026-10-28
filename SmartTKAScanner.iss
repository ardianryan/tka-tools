; Script generated for Inno Setup 6
; Smart TKA Scanner & Auto-Uploader Installer

#define MyAppName "Smart TKA Scanner"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "TKA Tools Community"
#define MyAppURL "https://github.com/ardianryan/tka-tools"
#define MyAppExeName "SmartTKAScanner.exe"

[Setup]
AppId={{5E28B0E1-2D22-4BD4-86F9-1BA44C9C985A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
; PrivilegesRequired=lowest allows installation without admin prompt if needed
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=.
OutputBaseFilename=SmartTKAScanner-Setup-v1.0.1
SetupIconFile=static\favicon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\SmartTKAScanner\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Note: Don't use "Flags: ignoreversion" on any shared system files

[Dirs]
Name: "{app}\inbox"; Permissions: users-full
Name: "{app}\processed"; Permissions: users-full
Name: "{app}\processed\duplicates"; Permissions: users-full
Name: "{app}\logs"; Permissions: users-full
Name: "{app}\temp_uploads"; Permissions: users-full

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\static\favicon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\static\favicon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
