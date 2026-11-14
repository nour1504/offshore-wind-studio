# Builds the Linux installers from Windows: the interface (Vite) into backend/src/owstudio/web, then
# the rest in the WSL distribution OffshoreWindStudio-Build (AlmaLinux 8, glibc 2.28) with
# packaging/linux/build-linux.sh: tests, PyInstaller, glibc check, .deb, .run.
# Results: dist\linux\offshore-wind-studio_<version>_amd64.deb and
# dist\linux\OffshoreWindStudio-<version>-linux-setup.run.
# The build distribution is prepared once (packaging/linux/setup-env.sh build); the engine
# distribution is never used here.
# Run:  powershell -ExecutionPolicy Bypass -File packaging\build-linux.ps1 [-SkipTests]

param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Distro = "OffshoreWindStudio-Build"
. (Join-Path $PSScriptRoot "interface.ps1")

$Known = (wsl.exe --list --quiet) -replace "`0", "" | Where-Object { $_.Trim() -eq $Distro }
if (-not $Known) { throw "The WSL distribution $Distro does not exist: see README, Linux version." }

Write-Host "Interface"
Build-Interface $Root

# The repository as Linux sees it: C:\a b -> /mnt/c/a b
$Drive = $Root.Substring(0, 1).ToLower()
$LinuxRoot = "/mnt/$Drive" + ($Root.Substring(2) -replace "\\", "/")
$Arguments = @("-d", $Distro, "-u", "root", "--exec", "bash", "$LinuxRoot/packaging/linux/build-linux.sh", $LinuxRoot)
if ($SkipTests) { $Arguments += "--skip-tests" }
Write-Host "Linux build in $Distro"
& wsl.exe @Arguments
if ($LASTEXITCODE -ne 0) { throw "Linux build failed" }
Get-ChildItem (Join-Path $Root "dist\linux") | Select-Object Name, Length
