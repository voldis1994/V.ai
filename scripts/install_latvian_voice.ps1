#Requires -Version 5.1
# Ieliek īstu latviešu balsi (Microsoft Everita / Nils) caur edge-tts — bez Windows valodas pakotnes.
param([switch]$AcceptDownloads)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$py = $null
foreach ($c in @(
    (Join-Path $root "release\win-x64\runtime-venv\Scripts\python.exe"),
    (Join-Path $root ".venv\Scripts\python.exe")
)) {
    if (Test-Path $c) { $py = $c; break }
}
if (-not $py) {
    Write-Host "[ERROR] Python venv nav atrasts. Palaid START_MAINBRAIN.bat vispirms." -ForegroundColor Red
    exit 1
}

Write-Host "Python: $py"
Write-Host "Instalē edge-tts (Microsoft Everita + Nils latviešu balsis)..."
& $py -m pip install --upgrade "edge-tts>=6.1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Pārbauda balsis..." -ForegroundColor Cyan
& $py -c @"
import asyncio, edge_tts
async def main():
    voices = await edge_tts.list_voices()
    lv = [v for v in voices if str(v.get('Locale','')).startswith('lv')]
    for v in lv:
        print(' ', v['ShortName'], '-', v.get('Gender'))
    assert any(v['ShortName']=='lv-LV-EveritaNeural' for v in lv), 'Trūkst Everita'
    print('OK: Everita pieejama')
asyncio.run(main())
"@
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Testē īsu frāzi (vajag internetu)..." -ForegroundColor Cyan
$env:PYTHONPATH = Join-Path $root "src\backend"
& $py -c @"
from mainbrain.tools.sense import speak_text, DEFAULT_LV_VOICE
print('Balss:', DEFAULT_LV_VOICE)
r = speak_text('Sveiki! Esmu Main Brain latviešu balsī.', lang='lv')
print(r)
assert r.get('ok'), r
"@
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] Testa atskaņošana neizdevās (tīkls / audio). edge-tts tomēr ir instalēts." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Gatavs. Main Brain tagad runā ar Everita (lv-LV-EveritaNeural)." -ForegroundColor Green
Write-Host "  pasaki sveiki"
Write-Host "  sameklē kas ir Python"
Write-Host ""
Write-Host "Piezīme: vajag internetu Edge TTS balsīm. Bez tīkla — SAPI fallback." -ForegroundColor DarkGray
