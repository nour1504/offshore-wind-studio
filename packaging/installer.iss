; Inno Setup script of the Offshore Wind Studio installer.
; Installs for the current user (no administrator rights), adds Start menu and optional desktop
; shortcuts, and an uninstaller. Uninstalling removes the program only: projects, results, input
; data and settings stay where they are (the data folder and %APPDATA%\OffshoreWindStudio).

#define AppName "Offshore Wind Studio"
#ifndef AppVersion
  #error AppVersion is given by build.ps1 (/DAppVersion=...)
#endif

[Setup]
AppId={{8E5B6C1A-3F0D-4C5E-9A37-0F3B2A9D6E41}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Offshore Wind Studio
DefaultDirName={localappdata}\Programs\Offshore Wind Studio
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist\installer
OutputBaseFilename=OffshoreWindStudio-{#AppVersion}-setup
SetupIconFile=owstudio.ico
UninstallDisplayIcon={app}\OffshoreWindStudio.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; An update replaces the program files as a whole: files of the previous version that this one
; no longer has (old interface bundles, libraries) would otherwise stay behind. Only program
; files live here; projects, data and settings are elsewhere.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\OffshoreWindStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\OffshoreWindStudio.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\OffshoreWindStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\OffshoreWindStudio.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[Code]
// Evergreen Runtime detection follows Microsoft's distribution documentation:
// https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution
function HasWebView2: Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := (RegQueryStringValue(HKCU, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'))
    or (RegQueryStringValue(HKLM32, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if not HasWebView2 then begin
    try
      DownloadTemporaryFile('https://go.microsoft.com/fwlink/p/?LinkId=2124703', 'MicrosoftEdgeWebview2Setup.exe', '', nil);
      if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
        Result := 'Microsoft Edge WebView2 Runtime could not be installed. https://developer.microsoft.com/microsoft-edge/webview2/'
      else if not HasWebView2 then
        Result := 'Please install Microsoft Edge WebView2 Evergreen Runtime, then run this installer again.';
    except
      Result := 'WebView2 Runtime download failed. Install it from https://developer.microsoft.com/microsoft-edge/webview2/ then try again.';
    end;
  end;
end;
