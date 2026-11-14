# Builds the interface (Vite) into backend/src/owstudio/web: the first step of build.ps1 and of
# build-linux.ps1, which load this file with:  . (Join-Path $PSScriptRoot "interface.ps1")

function Build-Interface([string]$Root) {
    $Node = (Get-Command node -ErrorAction Stop).Source
    $Web = [IO.Path]::GetFullPath((Join-Path $Root "backend\src\owstudio\web"))
    Push-Location (Join-Path $Root "frontend")
    try {
        & $Node node_modules\typescript\bin\tsc -b
        if ($LASTEXITCODE -ne 0) { throw "Type errors in the interface" }
        & $Node node_modules\vite\bin\vite.js build
        if ($LASTEXITCODE -ne 0) { throw "Interface build failed" }
    } finally { Pop-Location }
    if (Test-Path -LiteralPath $Web) {
        # Only the interface folder of this repository is ever deleted
        $Resolved = (Resolve-Path -LiteralPath $Web).Path
        $Inside = [IO.Path]::GetFullPath($Root) + [IO.Path]::DirectorySeparatorChar
        if ($Resolved -ne $Web -or -not $Resolved.StartsWith($Inside)) { throw "Unexpected interface target: $Resolved" }
        Remove-Item -LiteralPath $Resolved -Recurse -Force
    }
    Copy-Item -Recurse (Join-Path $Root "frontend\dist") $Web
}
