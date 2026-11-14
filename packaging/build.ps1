# Builds the Windows installer of Offshore Wind Studio.
#   1. the interface (Vite) into backend/src/owstudio/web
#   2. the application folder with PyInstaller (dist/OffshoreWindStudio)
#   3. the installer with Inno Setup (dist/installer/OffshoreWindStudio-<version>-setup.exe)
# Run from anywhere:  powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Nothing from the data folder or simulation results is included.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
. (Join-Path $PSScriptRoot "interface.ps1")
$Version = (Select-String -Path (Join-Path $Root "backend\src\owstudio\__init__.py") -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value

Write-Host "1/3 Interface"
Build-Interface $Root

Write-Host "2/3 Application folder"
& $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $Root "dist") --workpath (Join-Path $Root "build\pyinstaller") (Join-Path $PSScriptRoot "owstudio.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "3/3 Installer"
$Iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Iscc) {
    Write-Warning "Inno Setup 6 is not installed: the application folder is in dist\OffshoreWindStudio, the installer was not built."
    exit 0
}
& $Iscc "/DAppVersion=$Version" (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Installer: dist\installer\OffshoreWindStudio-$Version-setup.exe"
