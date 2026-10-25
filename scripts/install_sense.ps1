#Requires -Version 5.1
# Installs OpenCV for local camera + face detection (optional sense stack).
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
    Write-Host "[ERROR] Python venv not found. Run START_MAINBRAIN.bat first." -ForegroundColor Red
    exit 1
}

Write-Host "Python: $py"
Write-Host "Installing opencv-python-headless (camera + faces)..."
& $py -m pip install --upgrade "opencv-python-headless>=4.8"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Installing edge-tts (latviešu Everita / Nils balsis)..."
& $py -m pip install --upgrade "edge-tts>=6.1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $py -c "import cv2; print('OpenCV', cv2.__version__, 'OK')"
& $py -c "import edge_tts; print('edge-tts OK — Everita latviešu balss')"
Write-Host ""
Write-Host "Done. Try in Main Brain:" -ForegroundColor Green
Write-Host "  ko tu redzi kamerā"
Write-Host "  izveido sejas atpazīšanas programmu"
Write-Host "  pasaki sveiki"
Write-Host "  (vai scripts\install_latvian_voice.ps1 — tikai balsij)"
