#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:PYTHONPATH = Join-Path $root "src\backend"
$env:MAINBRAIN_API_TOKEN = [guid]::NewGuid().ToString("N")
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "Startē lokālo backend http://127.0.0.1:8765 ..."
Start-Process -FileName $py -ArgumentList "-m","mainbrain.api" -WorkingDirectory $root -WindowStyle Hidden

Write-Host "Startē WPF lietotni..."
dotnet run --project (Join-Path $root "src\desktop\MainBrain.Desktop\MainBrain.Desktop.csproj") -c Debug
