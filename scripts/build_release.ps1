#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
. (Join-Path $PSScriptRoot "Find-Python.ps1")

$out = Join-Path $root "release\win-x64"
New-Item -ItemType Directory -Force -Path $out | Out-Null

Write-Host "Building MainBrain.exe (win-x64)..."
$proj = Join-Path $root "src\desktop\MainBrain.Desktop\MainBrain.Desktop.csproj"
& dotnet publish $proj -c Release -r win-x64 --self-contained false -o $out
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] dotnet publish failed with code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

$exe = Join-Path $out "MainBrain.exe"
if (-not (Test-Path $exe)) {
    Write-Host "[ERROR] MainBrain.exe missing after publish: $exe" -ForegroundColor Red
    Get-ChildItem $out | ForEach-Object { Write-Host "  - $($_.Name)" }
    exit 1
}
Write-Host "[OK] $exe" -ForegroundColor Green

Write-Host "Copying Python backend..."
$backendOut = Join-Path $out "backend"
New-Item -ItemType Directory -Force -Path $backendOut | Out-Null
Copy-Item -Recurse -Force (Join-Path $root "src\backend\mainbrain") (Join-Path $backendOut "mainbrain")
Copy-Item -Force (Join-Path $root "pyproject.toml") $out
Copy-Item -Force (Join-Path $root "README.md") $out

# Prefer repo .venv if it is 3.12/3.13; else find/install system 3.12
$py = $null
$repoVenv = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $repoVenv) {
    $vv = & $repoVenv --version 2>&1 | Out-String
    if ($vv -match 'Python\s+(3\.12\.|3\.13\.)') {
        $py = @{ Exe = $repoVenv; Args = @(); Version = $Matches[0] }
    }
}
if (-not $py) {
    $py = Find-SupportedPython
}
if (-not $py) {
    Write-Host "Installing Python 3.12 for release runtime..."
    $cache = Join-Path $env:LOCALAPPDATA "MainBrainOS\bootstrap-cache"
    $py = Install-Python312 -CacheDir $cache
}
if (-not $py) {
    Write-Host "[ERROR] Need Python 3.12 or 3.13. Python 3.14 is NOT supported." -ForegroundColor Red
    exit 1
}
Write-Host "Release Python: $($py.Exe) $($py.Args -join ' ') ($($py.Version))"

$venv = Join-Path $out "runtime-venv"
if (Test-Path $venv) { Remove-Item -Recurse -Force $venv }
& $py.Exe @($py.Args + @("-m", "venv", $venv))
if ($LASTEXITCODE -ne 0) { Write-Host "[ERROR] runtime-venv create failed"; exit 1 }

$rtPy = Join-Path $venv "Scripts\python.exe"
& $rtPy -m pip install -U pip wheel setuptools
if ($LASTEXITCODE -ne 0) { exit 1 }

# Prefer binary wheels; do not compile from source on exotic Python
& $rtPy -m pip install --only-binary=:all: `
  "fastapi==0.115.6" "uvicorn[standard]==0.34.0" "pydantic==2.10.4" "pydantic-settings==2.7.0" `
  "httpx==0.28.1" "websockets==14.1" "langgraph==0.2.60" "langchain-core==0.3.28" `
  "aiosqlite==0.20.0" "pyyaml==6.0.2" "psutil==6.1.1" "orjson==3.10.12" `
  "python-multipart==0.0.20" "rich==13.9.4" "jinja2==3.1.5"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARN] only-binary install failed; retry without only-binary on Python $($py.Version)"
    & $rtPy -m pip install `
      "fastapi==0.115.6" "uvicorn[standard]==0.34.0" "pydantic==2.10.4" "pydantic-settings==2.7.0" `
      "httpx==0.28.1" "websockets==14.1" "langgraph==0.2.60" "langchain-core==0.3.28" `
      "aiosqlite==0.20.0" "pyyaml==6.0.2" "psutil==6.1.1" "orjson==3.10.12" `
      "python-multipart==0.0.20" "rich==13.9.4" "jinja2==3.1.5"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] pip install failed. Use Python 3.12 (not 3.14)." -ForegroundColor Red
        exit 1
    }
}

New-Item -ItemType Directory -Force -Path (Join-Path $out "python") | Out-Null

$manifest = @{
  name = "MainBrainOS"
  version = "1.1.1"
  exe = "MainBrain.exe"
  api = "http://127.0.0.1:8765"
  backend = "backend"
  python = "runtime-venv\Scripts\python.exe"
  data_dir = "%LOCALAPPDATA%\MainBrainOS"
  built_at = (Get-Date).ToString("o")
  notes = "Daily use: MainBrain.exe. AI: llama-server + GGUF. No Ollama required."
} | ConvertTo-Json
Set-Content -Path (Join-Path $out "manifest.json") -Value $manifest -Encoding UTF8

@"
Main Brain OS - release
1. Run MainBrain.exe (or Desktop shortcut)
2. Models: %LOCALAPPDATA%\MainBrainOS\models
3. llama-server: %LOCALAPPDATA%\MainBrainOS\llama
"@ | Set-Content (Join-Path $out "README_RELEASE.txt") -Encoding ASCII

if (-not (Test-Path $exe)) {
    Write-Host "[ERROR] MainBrain.exe missing at end: $exe" -ForegroundColor Red
    exit 1
}

Write-Host "Release folder: $out" -ForegroundColor Green
Write-Host "Executable: $exe"
exit 0
