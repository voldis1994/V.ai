#Requires -Version 5.1
# Thin wrapper -> full setup (ASCII-only for Windows PowerShell 5.1)
param(
    [switch]$SkipModels,
    [switch]$SkipLaunch,
    [ValidateSet("light", "standard", "capable")]
    [string]$ModelProfile = "standard"
)
$here = $PSScriptRoot
$setup = Join-Path $here "setup_full.ps1"
if (-not (Test-Path $setup)) {
    Write-Host "[ERROR] Missing setup_full.ps1" -ForegroundColor Red
    exit 1
}
$argsList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $setup, "-ModelProfile", $ModelProfile)
if ($SkipModels) { $argsList += "-SkipModels" }
if ($SkipLaunch) { $argsList += "-SkipLaunch" }
& powershell @argsList
exit $LASTEXITCODE
