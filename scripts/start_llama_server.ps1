#Requires -Version 5.1
<#
.SYNOPSIS
  Palaiž primāro llama.cpp llama-server ar GGUF no MainBrainOS models mapes.
#>
param(
    [string]$ModelPath = "",
    [int]$Port = 8080,
    [string]$HostAddress = "127.0.0.1",
    [int]$CtxSize = 4096,
    [switch]$InstallIfMissing
)

$ErrorActionPreference = "Stop"
$data = Join-Path $env:LOCALAPPDATA "MainBrainOS"
$llamaDir = Join-Path $data "llama"
$modelsDir = Join-Path $data "models"
$exe = Join-Path $llamaDir "llama-server.exe"

if (-not (Test-Path $exe)) {
    if ($InstallIfMissing) {
        $installer = Join-Path $PSScriptRoot "install_llama_server.ps1"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $installer -AcceptDownloads
    }
}
if (-not (Test-Path $exe)) {
    Write-Host "[KĻŪDA] llama-server.exe nav atrasts: $exe" -ForegroundColor Red
    Write-Host "Palaidiet: scripts\install_llama_server.ps1"
    exit 1
}

if (-not $ModelPath) {
    $roles = Join-Path $modelsDir "roles.json"
    if (Test-Path $roles) {
        $map = Get-Content $roles -Raw | ConvertFrom-Json
        if ($map.reasoning) { $ModelPath = [string]$map.reasoning }
        elseif ($map.coding) { $ModelPath = [string]$map.coding }
    }
}
if (-not $ModelPath -or -not (Test-Path $ModelPath)) {
    $gguf = Get-ChildItem $modelsDir -Filter "*.gguf" -ErrorAction SilentlyContinue |
        Sort-Object Length -Descending |
        Select-Object -First 1
    if ($gguf) { $ModelPath = $gguf.FullName }
}
if (-not $ModelPath -or -not (Test-Path $ModelPath)) {
    Write-Host "[KĻŪDA] Nav GGUF modeļa. Palaidiet download_models.ps1 vai ievietojiet .gguf mapē:" -ForegroundColor Red
    Write-Host "  $modelsDir"
    exit 1
}

Write-Host "=== Main Brain OS — llama-server (primārā inference) ===" -ForegroundColor Cyan
Write-Host "Exe:    $exe"
Write-Host "Modelis:$ModelPath"
Write-Host "API:    http://${HostAddress}:${Port}/v1"

# Ja jau klausās — nestartē otru
try {
    $r = Invoke-WebRequest -Uri "http://${HostAddress}:${Port}/v1/models" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -lt 500) {
        Write-Host "[OK] llama-server jau darbojas uz portu $Port" -ForegroundColor Green
        exit 0
    }
} catch {}

$args = @(
    "-m", $ModelPath,
    "--host", $HostAddress,
    "--port", "$Port",
    "-c", "$CtxSize"
)
Start-Process -FilePath $exe -ArgumentList $args -WorkingDirectory $llamaDir -WindowStyle Minimized
Write-Host "Gaida servera startu..."
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://${HostAddress}:${Port}/v1/models" -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -lt 500) {
            Write-Host "[OK] llama-server gatavs" -ForegroundColor Green
            exit 0
        }
    } catch {}
}
Write-Host "[BRĪDINĀJUMS] Serveris vēl neatbild — pārbaudiet procesu/žurnālus" -ForegroundColor Yellow
exit 0
