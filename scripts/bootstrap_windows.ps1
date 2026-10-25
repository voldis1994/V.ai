#Requires -Version 5.1
<#
.SYNOPSIS
  Main Brain OS — automātiska Windows atkarību lejupielāde un uzstādīšana.
.DESCRIPTION
  Pārbauda/instalē: winget rīkus, .NET 8 SDK, Python 3.12+, WebView2 Runtime,
  projekta .venv, pip atkarības, datu mapes.
  GGUF modeļus lejupielādē TIKAI ar -DownloadModels (vai START_MAINBRAIN.bat izvēli),
  jo tie ir lieli un ir licences nosacījumi.
#>
param(
    [switch]$SkipStart,
    [switch]$IncludeDevTools,
    [switch]$AcceptDownloads,
    [switch]$DownloadModels,
    [ValidateSet("light", "standard")]
    [string]$ModelProfile = "light",
    [switch]$SkipLlamaServer
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[BRĪDINĀJUMS] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "[KĻŪDA] $msg" -ForegroundColor Red }

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Ensure-Dir($Path) {
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Get-RepoRoot {
    if ($PSScriptRoot) {
        return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
    }
    return (Get-Location).Path
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Download($Url, $OutFile) {
    Write-Host "Lejupielādē: $Url"
    Ensure-Dir (Split-Path $OutFile -Parent)
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

function Install-WithWinget($Id, $Name) {
    if (-not (Test-Command "winget")) { return $false }
    Write-Host "Mēģina winget instalēt: $Name ($Id)"
    $args = @(
        "install", "--id", $Id, "-e", "--accept-package-agreements",
        "--accept-source-agreements", "--disable-interactivity"
    )
    & winget @args
    return ($LASTEXITCODE -eq 0 -or $LASTEXITCODE -eq -1978335189) # already installed codes vary
}

$root = Get-RepoRoot
Set-Location $root
$cache = Join-Path $env:LOCALAPPDATA "MainBrainOS\bootstrap-cache"
$data = Join-Path $env:LOCALAPPDATA "MainBrainOS"
Ensure-Dir $cache
Ensure-Dir $data
Ensure-Dir (Join-Path $data "models")
Ensure-Dir (Join-Path $data "logs")
Ensure-Dir (Join-Path $data "captures")

Write-Host "Main Brain OS bootstrap" -ForegroundColor Cyan
Write-Host "Repo: $root"
Write-Host "Dati: $data"
Write-Host "Administrators: $(Test-IsAdmin)"

if (-not $AcceptDownloads) {
    Write-Host ""
    Write-Host "Šis skripts lejupielādēs un instalēs nepieciešamās Windows atkarības:" -ForegroundColor Yellow
    Write-Host "  - .NET 8 SDK (ja nav)"
    Write-Host "  - Python 3.12+ (ja nav)"
    Write-Host "  - Microsoft Edge WebView2 Runtime (ja nav)"
    Write-Host "  - Python virtuālā vide un pip pakotnes"
    if ($DownloadModels) {
        Write-Host "  - GGUF AI modeļi (profils: $ModelProfile, vairāki GB no Hugging Face)"
    } else {
        Write-Host "GGUF AI modeļi šajā režīmā netiek lejupielādēti (izvēlieties bat opciju ar modeļiem)."
    }
    Write-Host ""
    $ans = Read-Host "Turpināt? (J/N)"
    if ($ans -notmatch '^[jJyY]') {
        Write-Warn "Atcelts."
        exit 0
    }
}

# --- winget ---
Write-Step "Winget"
if (Test-Command "winget") {
    Write-Ok "winget pieejams"
    try { winget source update | Out-Null } catch { Write-Warn "winget source update neizdevās (turpina)" }
} else {
    Write-Warn "winget nav PATH. Izmantos tiešās lejupielādes."
}

# --- .NET 8 SDK ---
Write-Step ".NET 8 SDK"
$dotnetOk = $false
if (Test-Command "dotnet") {
    $ver = (& dotnet --version) 2>$null
    if ($ver -match '^8\.') {
        Write-Ok "dotnet $ver"
        $dotnetOk = $true
    } else {
        Write-Warn "Atrasts dotnet $ver (ieteicams 8.x). Mēģinās uzstādīt .NET 8 SDK."
    }
}
if (-not $dotnetOk) {
    $installed = Install-WithWinget "Microsoft.DotNet.SDK.8" ".NET 8 SDK"
    if (-not $installed) {
        $dotnetInstall = Join-Path $cache "dotnet-install.ps1"
        Invoke-Download "https://dot.net/v1/dotnet-install.ps1" $dotnetInstall
        & powershell -NoProfile -ExecutionPolicy Bypass -File $dotnetInstall -Channel 8.0 -InstallDir "$env:LOCALAPPDATA\dotnet"
        $env:PATH = "$env:LOCALAPPDATA\dotnet;$env:PATH"
        if (-not (Test-Command "dotnet")) {
            Write-Err "dotnet joprojām nav pieejams. Instalējiet manuāli: https://dotnet.microsoft.com/download/dotnet/8.0"
            exit 1
        }
    }
    # atsvaidzina PATH no machine/user
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")
    Write-Ok "dotnet: $((dotnet --version) 2>$null)"
}

# --- Python 3.12+ ---
Write-Step "Python 3.12+"
function Get-PythonExe {
    foreach ($c in @("py", "python", "python3")) {
        if (Test-Command $c) {
            try {
                if ($c -eq "py") {
                    $v = & py -3 --version 2>$null
                    if ($LASTEXITCODE -eq 0) { return @{ Cmd = "py"; Args = @("-3") } }
                } else {
                    $v = & $c --version 2>$null
                    if ($v -match 'Python 3\.(1[2-9]|[2-9][0-9])') {
                        return @{ Cmd = $c; Args = @() }
                    }
                }
            } catch {}
        }
    }
    return $null
}

$pyInfo = Get-PythonExe
if (-not $pyInfo) {
    $ok = Install-WithWinget "Python.Python.3.12" "Python 3.12"
    if (-not $ok) {
        $pyInstaller = Join-Path $cache "python-3.12.8-amd64.exe"
        # Oficiālais python.org Windows x64 installer
        Invoke-Download "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe" $pyInstaller
        Write-Host "Instalē Python (per-user, PATH)..."
        Start-Process -FilePath $pyInstaller -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0" -Wait
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("PATH", "User")
    }
    $pyInfo = Get-PythonExe
}
if (-not $pyInfo) {
    Write-Err "Python 3.12+ nav atrasts pēc instalācijas. Restartējiet termināli un palaidiet vēlreiz."
    exit 1
}
& $pyInfo.Cmd @($pyInfo.Args + "--version")
Write-Ok "Python gatavs"

# --- WebView2 ---
Write-Step "WebView2 Runtime"
$webviewKeys = @(
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
)
$webviewOk = $false
foreach ($k in $webviewKeys) {
    if (Test-Path $k) { $webviewOk = $true; break }
}
if ($webviewOk) {
    Write-Ok "WebView2 Runtime atrasts"
} else {
    $ok = Install-WithWinget "Microsoft.EdgeWebView2Runtime" "WebView2 Runtime"
    if (-not $ok) {
        $wv = Join-Path $cache "MicrosoftEdgeWebView2Setup.exe"
        # Evergreen Bootstrapper (oficiālā Microsoft saite)
        Invoke-Download "https://go.microsoft.com/fwlink/p/?LinkId=2124703" $wv
        Write-Host "Instalē WebView2..."
        Start-Process -FilePath $wv -ArgumentList "/silent", "/install" -Wait
    }
    Write-Ok "WebView2 instalācijas solis pabeigts (ja nepieciešams — restartējiet)"
}

# --- Git (noderīgs) ---
Write-Step "Git"
if (Test-Command "git") {
    Write-Ok "git pieejams"
} else {
    $null = Install-WithWinget "Git.Git" "Git"
}

# --- Projekta venv + pip ---
Write-Step "Python virtuālā vide un atkarības"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Veido .venv..."
    if ($pyInfo.Cmd -eq "py") {
        & py -3 -m venv (Join-Path $root ".venv")
    } else {
        & $pyInfo.Cmd -m venv (Join-Path $root ".venv")
    }
}
& $venvPython -m pip install -U pip wheel setuptools
if (Test-Path (Join-Path $root "pyproject.toml")) {
    if ($IncludeDevTools) {
        & $venvPython -m pip install -e ".[dev]"
    } else {
        & $venvPython -m pip install -e .
    }
} else {
    Write-Warn "pyproject.toml nav atrasts — iespējams, neesat repo saknē"
}
Write-Ok "Python pakotnes uzstādītas"

# --- NuGet atjaunošana desktop projektam (ja SDK ir) ---
Write-Step ".NET projektu atjaunošana"
if (Test-Path (Join-Path $root "MainBrainOS.sln")) {
    try {
        & dotnet restore (Join-Path $root "MainBrainOS.sln")
        Write-Ok "dotnet restore OK"
    } catch {
        Write-Warn "dotnet restore neizdevās: $_"
    }
}

# --- Primārā inference: llama.cpp ---
Write-Step "llama.cpp llama-server (PRIMĀRAIS AI)"
if (-not $SkipLlamaServer) {
    $llamaInstall = Join-Path $root "scripts\install_llama_server.ps1"
    if (Test-Path $llamaInstall) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $llamaInstall -AcceptDownloads
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "llama-server instalācija neizdevās — AI inference nebūs, līdz to uzstādīsiet"
        } else {
            Write-Ok "llama-server uzstādīts (%LOCALAPPDATA%\MainBrainOS\llama)"
        }
    } else {
        Write-Warn "Nav install_llama_server.ps1"
    }
} else {
    Write-Host "llama-server instalācija izlaista (-SkipLlamaServer)"
}

# --- GGUF modeļi ---
Write-Step "GGUF modeļi (llama.cpp)"
$modelsDir = Join-Path $data "models"
Ensure-Dir $modelsDir
Write-Host "Modeļu mape: $modelsDir"
if ($DownloadModels) {
    $dl = Join-Path $root "scripts\download_models.ps1"
    if (-not (Test-Path $dl)) {
        Write-Err "Nav atrasts scripts\download_models.ps1"
        exit 1
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $dl -Profile $ModelProfile -AcceptDownloads -ModelsDir $modelsDir
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Modeļu lejupielāde beidzās ar kļūdu — pārējā uzstādīšana turpinās"
    }
    # Palaid llama-server ar lejupielādēto modeli
    $startLlama = Join-Path $root "scripts\start_llama_server.ps1"
    if (Test-Path $startLlama) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $startLlama -InstallIfMissing
    }
} else {
    Write-Host "GGUF nav lejupielādēti. START_MAINBRAIN.bat → opcija 4/5/6"
    Write-Host "  vai: scripts\download_models.ps1 -Profile light"
}
Write-Host "Ollama NAV nepieciešama. Tā ir tikai neobligāta rezerve (MAINBRAIN_OLLAMA_ENABLED=true)."

# --- Kopsavilkums ---
Write-Step "Kopsavilkums"
Write-Host "Repo:     $root"
Write-Host "venv:     $venvPython"
Write-Host "Dati:     $data"
Write-Host "Modeļi:   $modelsDir"
Write-Ok "Bootstrap pabeigts"

# Saglabā statusu
$status = @{
    finished_at = (Get-Date).ToString("o")
    root = $root
    data = $data
    dotnet = ((& dotnet --version) 2>$null)
    python = ((& $venvPython --version) 2>$null)
} | ConvertTo-Json
Set-Content -Path (Join-Path $data "bootstrap_status.json") -Value $status -Encoding UTF8

if (-not $SkipStart) {
    $startPs1 = Join-Path $root "scripts\start_dev.ps1"
    if (Test-Path $startPs1) {
        Write-Step "Palaiž izstrādes vidi"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $startPs1
    } else {
        Write-Warn "start_dev.ps1 nav atrasts — palaidiet MainBrain.exe manuāli pēc būvēšanas"
    }
}
