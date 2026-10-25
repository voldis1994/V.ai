#Requires -Version 5.1
# Ieliek istu latviesu balsi (Microsoft Everita / Nils) caur edge-tts.
# Bez Windows valodas pakotnes. Bez iegulta Python koda PowerShell faila.
param([switch]$AcceptDownloads)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$scripts = $PSScriptRoot

$py = $null
foreach ($c in @(
    (Join-Path $root "release\win-x64\runtime-venv\Scripts\python.exe"),
    (Join-Path $root ".venv\Scripts\python.exe")
)) {
    if (Test-Path -LiteralPath $c) {
        $py = $c
        break
    }
}
if (-not $py) {
    Write-Host "[ERROR] Python venv nav atrasts. Palaid START_MAINBRAIN.bat vispirms." -ForegroundColor Red
    exit 1
}

Write-Host "Python: $py"
Write-Host "Instale edge-tts (Microsoft Everita + Nils latviesu balsis)..."
& $py -m pip install --upgrade "edge-tts>=6.1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Parbauda balsis..." -ForegroundColor Cyan
& $py (Join-Path $scripts "_check_lv_voices.py")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Teste isu frazi (vajag internetu)..." -ForegroundColor Cyan
$env:PYTHONPATH = Join-Path $root "src\backend"
& $py (Join-Path $scripts "_test_lv_speak.py")
$speakCode = $LASTEXITCODE
if ($speakCode -ne 0) {
    Write-Host "[WARN] Testa atskanosana neizdevas (tikls / audio). edge-tts tomer ir instalets." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Gatavs. Main Brain tagad runa ar Everita (lv-LV-EveritaNeural)." -ForegroundColor Green
Write-Host "  pasaki sveiki"
Write-Host "  samekle kas ir Python"
Write-Host ""
Write-Host "Piezime: vajag internetu Edge TTS balsim. Bez tikla — SAPI fallback." -ForegroundColor DarkGray
exit 0
