# Only called after an explicit local-engine setup request. Changes Windows features only.
param([Parameter(Mandatory=$true)][string]$ResultFile)
$ErrorActionPreference = 'Stop'
try {
    $changed = $false
    foreach ($featureName in @('Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform')) {
        $feature = Get-WindowsOptionalFeature -Online -FeatureName $featureName
        if ($feature.State -ne 'Enabled') {
            Enable-WindowsOptionalFeature -Online -FeatureName $featureName -All -NoRestart | Out-Null
            $changed = $true
        }
    }
    & wsl.exe --install --no-distribution --web-download 2>&1 | Out-File -LiteralPath ($ResultFile + '.log') -Encoding utf8
    $wslExit = $LASTEXITCODE
    if ($wslExit -notin @(0, 3010) -and -not $changed) { throw "WSL setup failed: $wslExit; see $ResultFile.log" }
    $result = @{state = $(if ($changed -or $wslExit -eq 3010) {'needs_restart'} else {'ready'}); error = $null}
} catch {
    $result = @{state = 'failed'; error = $_.Exception.Message}
}
$result | ConvertTo-Json | Set-Content -LiteralPath $ResultFile -Encoding UTF8
