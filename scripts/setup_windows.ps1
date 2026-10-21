#Requires -Version 5.1
$ErrorActionPreference = "Stop"
Write-Host "=== Main Brain OS — Windows uzstādīšana ===" -ForegroundColor Cyan

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Pārbauda .NET SDK..."
if (-not (Test-Command "dotnet")) {
    Write-Host "KĻŪDA: dotnet nav PATH. Instalējiet .NET 8 LTS." -ForegroundColor Red
    exit 1
}
dotnet --info | Out-Host

Write-Host "Pārbauda Python 3.12+..."
if (-not (Test-Command "python")) {
    Write-Host "KĻŪDA: python nav PATH." -ForegroundColor Red
    exit 1
}
python --version

Write-Host "Veido virtuālo vidi..."
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
$py = Join-Path $root ".venv\Scripts\python.exe"
& $py -m pip install -U pip
& $py -m pip install -e ".[dev]"

Write-Host "Pārbauda WebView2 Runtime..."
$webviewKey = "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
if (-not (Test-Path $webviewKey)) {
    Write-Host "BRĪDINĀJUMS: WebView2 Runtime nav atrasts. Instalējiet Microsoft Edge WebView2 Runtime." -ForegroundColor Yellow
} else {
    Write-Host "WebView2 Runtime atrasts."
}

$data = Join-Path $env:LOCALAPPDATA "MainBrainOS"
New-Item -ItemType Directory -Force -Path $data, (Join-Path $data "models"), (Join-Path $data "logs") | Out-Null
Write-Host "Datu mape: $data"

Write-Host "Uzstādīšana pabeigta. Palaidiet scripts/start_dev.ps1" -ForegroundColor Green
