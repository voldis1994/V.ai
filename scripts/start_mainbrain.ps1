#Requires -Version 5.1
<#
.SYNOPSIS
  Main Brain OS — uzstādīšana un palaišana (Windows).
  Primārā AI: llama.cpp llama-server + GGUF (Ollama nav vajadzīga).
#>
param(
    [ValidateSet("1","2","3","4","5","6","7","")]
    [string]$Choice = ""
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root "scripts\bootstrap_windows.ps1"))) {
    Write-Host "[KLUDA] Nav atrasts scripts\bootstrap_windows.ps1" -ForegroundColor Red
    Write-Host "Palaidiet no repo saknes (kur ir START_MAINBRAIN.bat)." -ForegroundColor Yellow
    Write-Host "Aktuala mape: $root"
    exit 1
}

Set-Location $root

function Show-Menu {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  Main Brain OS — sakuma instalacija"
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Primara AI: llama.cpp llama-server + GGUF"
    Write-Host "Ollama NAV nepieciesama (tikai rezerv)."
    Write-Host ""
    Write-Host "Izvele:"
    Write-Host "  [1] Uzstadit rikus un palaist (bez GGUF)"
    Write-Host "  [2] Tikai uzstadit rikus (bez GGUF, nepalaiž)"
    Write-Host "  [3] Uzstadit rikus + izstrades testu pakotnes"
    Write-Host "  [4] Uzstadit rikus + GGUF light (~2 GB) un palaist   <— IETEICAMS"
    Write-Host "  [5] Uzstadit rikus + GGUF standard (~6-10 GB) un palaist"
    Write-Host "  [6] Tikai lejupieladet GGUF light modelus"
    Write-Host "  [7] Atcelt"
    Write-Host ""
}

if (-not $Choice) {
    Show-Menu
    $Choice = Read-Host "Ievadiet numuru"
}

$bootstrap = Join-Path $root "scripts\bootstrap_windows.ps1"
$download = Join-Path $root "scripts\download_models.ps1"

switch ($Choice) {
    "1" {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap -AcceptDownloads
    }
    "2" {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap -AcceptDownloads -SkipStart
    }
    "3" {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap -AcceptDownloads -IncludeDevTools
    }
    "4" {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap -AcceptDownloads -DownloadModels -ModelProfile light
    }
    "5" {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $bootstrap -AcceptDownloads -DownloadModels -ModelProfile standard
    }
    "6" {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $download -Profile light -AcceptDownloads
    }
    "7" {
        Write-Host "Atcelts."
        exit 0
    }
    default {
        Write-Host "[KLUDA] Nederiga izvele: $Choice" -ForegroundColor Red
        exit 1
    }
}

$code = $LASTEXITCODE
Write-Host ""
if ($code -ne 0 -and $null -ne $code) {
    Write-Host "[KLUDA] Process beidzas ar kodu $code" -ForegroundColor Red
    exit $code
}

Write-Host "Gatavs." -ForegroundColor Green
Write-Host "llama-server: $env:LOCALAPPDATA\MainBrainOS\llama"
Write-Host "GGUF:         $env:LOCALAPPDATA\MainBrainOS\models"
Write-Host "API:          http://127.0.0.1:8080/v1"
Write-Host "Ja serveris nav startējis: scripts\start_llama_server.ps1"
exit 0
