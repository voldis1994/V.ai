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

Write-Host "Kopē Python backend (portatīvi, bez .venv prasības Git mapē)..."
$backendOut = Join-Path $out "backend"
New-Item -ItemType Directory -Force -Path $backendOut | Out-Null
Copy-Item -Recurse -Force (Join-Path $root "src\backend\mainbrain") (Join-Path $backendOut "mainbrain")
Copy-Item -Force (Join-Path $root "pyproject.toml") $out
Copy-Item -Force (Join-Path $root "README.md") $out

# Izveido laidiena venv blakus exe
$venv = Join-Path $out "runtime-venv"
if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
python -m venv $venv
& (Join-Path $venv "Scripts\python.exe") -m pip install -U pip
& (Join-Path $venv "Scripts\python.exe") -m pip install `
  "fastapi==0.115.6" "uvicorn[standard]==0.34.0" "pydantic==2.10.4" "pydantic-settings==2.7.0" `
  "httpx==0.28.1" "websockets==14.1" "langgraph==0.2.60" "langchain-core==0.3.28" `
  "aiosqlite==0.20.0" "pyyaml==6.0.2" "psutil==6.1.1" "orjson==3.10.12" `
  "python-multipart==0.0.20" "rich==13.9.4" "jinja2==3.1.5"

# Ērts python.exe ceļš laidienam
New-Item -ItemType Directory -Force -Path (Join-Path $out "python") | Out-Null
Copy-Item (Join-Path $venv "Scripts\python.exe") (Join-Path $out "python\python.exe") -ErrorAction SilentlyContinue
# Pilna venv paliek runtime-venv; BackendHost meklē python\python.exe un .venv

$manifest = @{
  name = "MainBrainOS"
  version = "1.1.0"
  exe = "MainBrain.exe"
  api = "http://127.0.0.1:8765"
  backend = "backend"
  python = "runtime-venv\Scripts\python.exe"
  data_dir = "%LOCALAPPDATA%\MainBrainOS"
  built_at = (Get-Date).ToString("o")
  notes = "Palaist ārpus Git repo. Modeļi lokāli. Nav mākoņa API."
} | ConvertTo-Json
Set-Content -Path (Join-Path $out "manifest.json") -Value $manifest -Encoding UTF8

@"
# Main Brain OS — laidiena palaišana

1. Pārliecinieties, ka ir instalēts .NET 8 Desktop Runtime un WebView2.
2. Palaidiet MainBrain.exe
3. Modeļus ievietojiet %LOCALAPPDATA%\MainBrainOS\models
4. Dati/žurnāli: %LOCALAPPDATA%\MainBrainOS

Bez interneta AI inference darbojas tikai ar lokālu llama-server/Ollama.
"@ | Set-Content (Join-Path $out "PALAIDES_LV.txt") -Encoding UTF8

Get-ChildItem $out -Recurse -File | Where-Object { $_.FullName -notmatch "runtime-venv" } | ForEach-Object {
  $hash = Get-FileHash $_.FullName -Algorithm SHA256
  "{0}  {1}" -f $hash.Hash, $_.FullName.Substring($out.Length + 1)
} | Set-Content (Join-Path $out "SHA256SUMS.txt")

Write-Host "Laidiena mape: $out" -ForegroundColor Green
Write-Host "Galvenais izpildfails: $(Join-Path $out 'MainBrain.exe')"
