; Inno Setup script: builds AutocorrectSetup.exe from dist\Autocorrect (PyInstaller output).
; Per-user install: no administrator password needed.

#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6C1F0E52-4B7B-4C2E-9C1B-8A2B1E3A9D41}
AppName=Autocorrect
AppVersion={#AppVersion}
AppPublisher=Autocorrect
DefaultDirName={localappdata}\Programs\Autocorrect
DefaultGroupName=Autocorrect
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=AutocorrectSetup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Autocorrect.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=force

[Languages]
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
hebrew.StartupTask=להפעיל את Autocorrect אוטומטית עם הפעלת המחשב (מומלץ)
english.StartupTask=Start Autocorrect automatically when Windows starts (recommended)
hebrew.LaunchNow=להפעיל את Autocorrect עכשיו
english.LaunchNow=Launch Autocorrect now

[Tasks]
Name: "startup"; Description: "{cm:StartupTask}"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\Autocorrect\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Autocorrect"; Filename: "{app}\Autocorrect.exe"
Name: "{userdesktop}\Autocorrect"; Filename: "{app}\Autocorrect.exe"; Tasks: desktopicon
Name: "{userstartup}\Autocorrect"; Filename: "{app}\Autocorrect.exe"; Tasks: startup

[Run]
Filename: "{app}\Autocorrect.exe"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/im Autocorrect.exe /f"; Flags: runhidden; RunOnceId: "KillApp"
