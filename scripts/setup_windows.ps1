#Requires -Version 5.1
# Savietojamības ietinums - pilnā lejupielāde/instalācija ir bootstrap_windows.ps1
$ErrorActionPreference = "Stop"
$bootstrap = Join-Path $PSScriptRoot "bootstrap_windows.ps1"
if (-not (Test-Path $bootstrap)) {
    Write-Host "KĻŪDA: nav atrasts bootstrap_windows.ps1" -ForegroundColor Red
    exit 1
}
Write-Host "=== Main Brain OS - Windows uzstādīšana (caur bootstrap) ===" -ForegroundColor Cyan
& powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap -AcceptDownloads -SkipStart -IncludeDevTools
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Uzstādīšana pabeigta. Palaidiet START_MAINBRAIN.bat vai scripts/start_dev.ps1" -ForegroundColor Green
