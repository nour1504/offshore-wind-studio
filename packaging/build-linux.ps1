# Builds the Linux installers of Offshore Wind Studio from Windows.
#   1. the interface (Vite) into backend/src/owstudio/web, as for Windows;
#   2. everything else inside the dedicated WSL distribution OffshoreWindStudio-Build (AlmaLinux 8,
#      glibc 2.28), with packaging/linux/build-linux.sh: tests, PyInstaller, glibc check, .deb, .run.
# Results: dist\linux\offshore-wind-studio_<version>_amd64.deb and
#          dist\linux\OffshoreWindStudio-<version>-linux-setup.run
# The build distribution is prepared once with packaging/linux/setup-env.sh build (see README).
# The engine distribution (OffshoreWindStudio-WRF) is never used here.
# Run:  powershell -ExecutionPolicy Bypass -File packaging\build-linux.ps1 [-SkipTests]

param([switch]$SkipTests)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Node = (Get-Command node -ErrorAction Stop).Source
$Web = Join-Path $Root "backend\src\owstudio\web"
$Distro = "OffshoreWindStudio-Build"

$Known = (wsl.exe --list --quiet) -replace "`0", "" | Where-Object { $_.Trim() -eq $Distro }
if (-not $Known) { throw "The WSL distribution $Distro does not exist: see README, Linux version." }

Write-Host "Interface"
Push-Location (Join-Path $Root "frontend")
try {
    & $Node node_modules\typescript\bin\tsc -b
    if ($LASTEXITCODE -ne 0) { throw "Type errors in the interface" }
    & $Node node_modules\vite\bin\vite.js build
    if ($LASTEXITCODE -ne 0) { throw "Interface build failed" }
} finally { Pop-Location }
if (Test-Path -LiteralPath $Web) {
    $ResolvedWeb = (Resolve-Path -LiteralPath $Web).Path
    $ExpectedWeb = [IO.Path]::GetFullPath((Join-Path $Root "backend\src\owstudio\web"))
    if ($ResolvedWeb -ne $ExpectedWeb) { throw "Unexpected interface target: $ResolvedWeb" }
    Remove-Item -LiteralPath $ResolvedWeb -Recurse -Force
}
Copy-Item -Recurse (Join-Path $Root "frontend\dist") $Web

# The repository as Linux sees it: C:\a b -> /mnt/c/a b
$Drive = $Root.Substring(0, 1).ToLower()
$LinuxRoot = "/mnt/$Drive" + ($Root.Substring(2) -replace "\\", "/")
$Arguments = @("-d", $Distro, "-u", "root", "--exec", "bash", "$LinuxRoot/packaging/linux/build-linux.sh", $LinuxRoot)
if ($SkipTests) { $Arguments += "--skip-tests" }
Write-Host "Linux build in $Distro"
& wsl.exe @Arguments
if ($LASTEXITCODE -ne 0) { throw "Linux build failed" }
Get-ChildItem (Join-Path $Root "dist\linux") | Select-Object Name, Length
