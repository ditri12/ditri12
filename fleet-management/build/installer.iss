; סקריפט Inno Setup לבניית קובץ ההתקנה של "ניהול צי רכב"
; בנייה: ISCC.exe /DAppVersion=1.0.0 /DSourceDir=..\dist build\installer.iss

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist"
#endif

[Setup]
AppId={{7B1E2C44-9D7A-4C1E-9F62-3A5C8E1D2B47}
AppName=ניהול צי רכב
AppVersion={#AppVersion}
AppVerName=ניהול צי רכב {#AppVersion}
AppPublisher=Fleet Manager
DefaultDirName={autopf}\FleetManager
DefaultGroupName=ניהול צי רכב
UninstallDisplayName=ניהול צי רכב
UninstallDisplayIcon={app}\FleetManager.exe
OutputDir=..\dist
OutputBaseFilename=FleetManager-Setup-{#AppVersion}
SetupIconFile=icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; התקנה למשתמש הנוכחי בלי צורך בהרשאות מנהל; אפשר לבחור התקנה לכל המשתמשים
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
ShowLanguageDialog=no
CloseApplications=yes

[Languages]
Name: "hebrew"; MessagesFile: "compiler:Languages\Hebrew.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\FleetManager.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ניהול צי רכב"; Filename: "{app}\FleetManager.exe"
Name: "{group}\{cm:UninstallProgram,ניהול צי רכב}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\ניהול צי רכב"; Filename: "{app}\FleetManager.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FleetManager.exe"; Description: "{cm:LaunchProgram,ניהול צי רכב}"; Flags: nowait postinstall skipifsilent

; הנתונים (%APPDATA%\FleetManager) נשמרים גם אחרי הסרת התוכנה, כדי שלא יאבדו בטעות
