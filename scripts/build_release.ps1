#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$out = Join-Path $root "release\win-x64"
New-Item -ItemType Directory -Force -Path $out | Out-Null

Write-Host "Būvē MainBrain.exe (win-x64)..."
dotnet publish `
  (Join-Path $root "src\desktop\MainBrain.Desktop\MainBrain.Desktop.csproj") `
  -c Release `
  -r win-x64 `
  --self-contained false `
  -o $out

Write-Host "Kopē Python backend..."
$backendOut = Join-Path $out "backend"
New-Item -ItemType Directory -Force -Path $backendOut | Out-Null
Copy-Item -Recurse -Force (Join-Path $root "src\backend\mainbrain") (Join-Path $backendOut "mainbrain")
Copy-Item -Force (Join-Path $root "pyproject.toml") $out

$manifest = @{
  name = "MainBrainOS"
  version = "1.0.0"
  exe = "MainBrain.exe"
  api = "http://127.0.0.1:8765"
  built_at = (Get-Date).ToString("o")
} | ConvertTo-Json
Set-Content -Path (Join-Path $out "manifest.json") -Value $manifest -Encoding UTF8

Get-ChildItem $out -Recurse -File | ForEach-Object {
  $hash = Get-FileHash $_.FullName -Algorithm SHA256
  "{0}  {1}" -f $hash.Hash, $_.FullName.Substring($out.Length + 1)
} | Set-Content (Join-Path $out "SHA256SUMS.txt")

Write-Host "Laidiena mape: $out" -ForegroundColor Green
Write-Host "Galvenais izpildfails: $(Join-Path $out 'MainBrain.exe')"
