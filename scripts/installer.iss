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

[Code]
var
  PurgeUserData: Boolean;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  PurgeUserData := False;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigPath, CachePath, LocalAppDataPath, AppDataPath, UserProfilePath: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    if not UninstallSilent then
    begin
      PurgeUserData := (MsgBox(
        'Do you also want to completely delete all downloaded translation models, caches, and user configurations?',
        mbConfirmation,
        MB_YESNO or MB_DEFBUTTON2
      ) = IDYES);
    end;
  end
  else if (CurUninstallStep = usPostUninstall) and PurgeUserData then
  begin
    LocalAppDataPath := ExpandConstant('{localappdata}');
    AppDataPath := ExpandConstant('{userappdata}');
    UserProfilePath := ExpandConstant('{userprofile}');

    ConfigPath := UserProfilePath + '\.config\subtitle-translator';
    if DirExists(ConfigPath) then
      DelTree(ConfigPath, True, True, True);

    CachePath := UserProfilePath + '\.cache\subtitle-translator';
    if DirExists(CachePath) then
      DelTree(CachePath, True, True, True);

    if DirExists(LocalAppDataPath + '\SubtitleTranslator') then
      DelTree(LocalAppDataPath + '\SubtitleTranslator', True, True, True);

    if DirExists(AppDataPath + '\subtitle-translator') then
      DelTree(AppDataPath + '\subtitle-translator', True, True, True);
  end;
end;
