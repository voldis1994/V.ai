#Requires -Version 5.1
# ASCII-only script (Windows PowerShell 5.1 safe without BOM issues).
# Full install: deps + llama-server + GGUF light + MainBrain.exe + Desktop shortcut.
param(
    [switch]$SkipModels,
    [switch]$SkipLaunch,
    [ValidateSet("light", "standard")]
    [string]$ModelProfile = "light"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Step($m) { Write-Host ""; Write-Host "=== $m ===" -ForegroundColor Cyan }
function Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Fail($m) { Write-Host "[ERROR] $m" -ForegroundColor Red; exit 1 }

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
Write-Host "Main Brain OS - FULL SETUP"
Write-Host "Repo: $root"
Write-Host "Primary AI: llama.cpp llama-server + GGUF (Ollama NOT required)"

$bootstrap = Join-Path $root "scripts\bootstrap_windows.ps1"
$build = Join-Path $root "scripts\build_release.ps1"
$llamaInstall = Join-Path $root "scripts\install_llama_server.ps1"
$llamaStart = Join-Path $root "scripts\start_llama_server.ps1"

if (-not (Test-Path $bootstrap)) { Fail "Missing scripts\bootstrap_windows.ps1 - use full GitHub main zip/clone" }

# 1) Dependencies (.NET, Python, WebView2, venv) - do not auto-start dev UI
Step "1/5 Install dependencies"
$bootArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $bootstrap, "-AcceptDownloads", "-SkipStart")
if (-not $SkipModels) {
    $bootArgs += @("-DownloadModels", "-ModelProfile", $ModelProfile)
}
& powershell @bootArgs
if ($LASTEXITCODE -ne 0) { Warn "Bootstrap reported exit $LASTEXITCODE - continuing if tools exist" }

# 2) llama-server
Step "2/5 Install llama-server"
if (Test-Path $llamaInstall) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $llamaInstall -AcceptDownloads
} else {
    Warn "install_llama_server.ps1 missing"
}

# 3) Build MainBrain.exe release
Step "3/5 Build MainBrain.exe"
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Fail "dotnet not found after bootstrap. Install .NET 8 SDK and re-run."
}
& powershell -NoProfile -ExecutionPolicy Bypass -File $build
if ($LASTEXITCODE -ne 0) { Fail "build_release.ps1 failed" }

$exe = Join-Path $root "release\win-x64\MainBrain.exe"
if (-not (Test-Path $exe)) { Fail "MainBrain.exe was not created at $exe" }
Ok "Built: $exe"

# 4) Desktop + Start Menu shortcuts for daily use
Step "4/5 Create shortcuts"
$workDir = Join-Path $root "release\win-x64"
$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null

function New-Shortcut($Path, $Target, $WorkDir) {
    $w = New-Object -ComObject WScript.Shell
    $s = $w.CreateShortcut($Path)
    $s.TargetPath = $Target
    $s.WorkingDirectory = $WorkDir
    $s.Description = "Main Brain OS"
    $s.Save()
}

$deskLnk = Join-Path $desktop "Main Brain OS.lnk"
$menuLnk = Join-Path $startMenu "Main Brain OS.lnk"
New-Shortcut $deskLnk $exe $workDir
New-Shortcut $menuLnk $exe $workDir
Ok "Desktop shortcut: $deskLnk"
Ok "Start Menu shortcut: $menuLnk"

# Also a tiny daily launcher bat next to exe
$dailyBat = Join-Path $workDir "START_MAINBRAIN_DAILY.bat"
@"
@echo off
cd /d "%~dp0"
start "" "%~dp0MainBrain.exe"
"@ | Set-Content -Path $dailyBat -Encoding ASCII
Ok "Daily bat: $dailyBat"

# 5) Start llama-server + app
Step "5/5 Launch"
if (Test-Path $llamaStart) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $llamaStart -InstallIfMissing
}
if (-not $SkipLaunch) {
    Write-Host "Starting MainBrain.exe ..."
    Start-Process -FilePath $exe -WorkingDirectory $workDir
}

Write-Host ""
Ok "DONE"
Write-Host "Daily use: double-click Desktop shortcut 'Main Brain OS'"
Write-Host "Or run: $exe"
Write-Host "Models:  $env:LOCALAPPDATA\MainBrainOS\models"
Write-Host "llama:   $env:LOCALAPPDATA\MainBrainOS\llama"
Write-Host "API:     http://127.0.0.1:8080/v1"
exit 0
