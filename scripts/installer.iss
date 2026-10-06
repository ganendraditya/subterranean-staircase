; Inno Setup Script for Subterranean Staircase Windows Installer
; Builds Subterranean-Staircase-windows-x64-Setup.exe

#define MyAppName "Subterranean Staircase"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Ganendra Aditya"
#define MyAppURL "https://github.com/ganendraditya/subterranean-staircase"
#define MyAppExeName "Subterranean Staircase.exe"

#ifndef AppSourceDir
#define AppSourceDir "..\dist\" + MyAppName
#endif

[Setup]
AppId={{5D076711-A528-44A3-9A2E-C18080C0B438}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\README.md
OutputDir=..\dist
OutputBaseFilename=Subterranean-Staircase-windows-x64-Setup
SetupIconFile=..\ui\assets\app_icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start Subterranean Staircase automatically at login"; GroupDescription: "Windows Startup:"; Flags: unchecked

[Files]
Source: "{#AppSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
