#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONPATH = Join-Path $root "src\backend"
$env:MAINBRAIN_API_TOKEN = [guid]::NewGuid().ToString("N")
# Primārā inference - llama.cpp; Ollama pēc noklusējuma IZSLĒGTA
$env:MAINBRAIN_OLLAMA_ENABLED = "false"
$env:MAINBRAIN_PRIMARY_PROVIDER = "llama.cpp"
$env:MAINBRAIN_LLAMA_BASE_URL = "http://127.0.0.1:8080/v1"

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "Startē llama-server (primārā AI)..." -ForegroundColor Cyan
$startLlama = Join-Path $root "scripts\start_llama_server.ps1"
if (Test-Path $startLlama) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $startLlama -InstallIfMissing
} else {
    Write-Host "[BRĪDINĀJUMS] start_llama_server.ps1 nav atrasts" -ForegroundColor Yellow
}

Write-Host "Startē lokālo backend http://127.0.0.1:8765 ..."
# Bērns manto $env:* no šīs sesijas
Start-Process -FileName $py -ArgumentList "-m","mainbrain.api" -WorkingDirectory $root -WindowStyle Hidden

Write-Host "Startē WPF lietotni..."
dotnet run --project (Join-Path $root "src\desktop\MainBrain.Desktop\MainBrain.Desktop.csproj") -c Debug
