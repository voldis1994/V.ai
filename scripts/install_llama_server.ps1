#Requires -Version 5.1
<#
.SYNOPSIS
  Lejupielādē un uzstāda llama.cpp `llama-server` Windows x64 (primārā Main Brain OS inference).
#>
param(
    [switch]$AcceptDownloads,
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Write-Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Write-Warn($m) { Write-Host "[BRĪDINĀJUMS] $m" -ForegroundColor Yellow }
function Write-Err($m) { Write-Host "[KĻŪDA] $m" -ForegroundColor Red }

if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "MainBrainOS\llama"
}
$cache = Join-Path $env:LOCALAPPDATA "MainBrainOS\bootstrap-cache"
New-Item -ItemType Directory -Force -Path $InstallDir, $cache | Out-Null

Write-Step "llama.cpp llama-server uzstādīšana"
Write-Host "Mērķis: $InstallDir"
Write-Host "Šis ir PRIMĀRAIS AI ceļš Main Brain OS (ne Ollama)."

if (-not $AcceptDownloads) {
    $ans = Read-Host "Lejupielādēt llama-server no GitHub Releases? (J/N)"
    if ($ans -notmatch '^[jJyY]') { Write-Warn "Atcelts."; exit 0 }
}

# Oficiālie llama.cpp release avoti (jaunākais → vecākais)
$apiUrls = @(
    "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest",
    "https://api.github.com/repos/ggerganov/llama.cpp/releases/latest"
)

$release = $null
foreach ($api in $apiUrls) {
    try {
        Write-Host "Vaicā: $api"
        $release = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = "MainBrainOS" }
        if ($release) { break }
    } catch {
        Write-Warn "Neizdevās: $_"
    }
}
if (-not $release) {
    Write-Err "Neizdevās nolasīt llama.cpp releases. Lejupielādējiet manuāli: https://github.com/ggml-org/llama.cpp/releases"
    exit 1
}

Write-Ok "Release: $($release.tag_name)"

# Preferē CPU/AVX2 Windows zip (plašāka savietojamība nekā CUDA)
$assets = @($release.assets)
$preferred = $assets | Where-Object {
    $_.name -match 'win' -and $_.name -match '\.zip$' -and (
        $_.name -match 'avx2' -or $_.name -match 'cpu' -or $_.name -match 'x64'
    ) -and ($_.name -notmatch 'cuda') -and ($_.name -notmatch 'vulkan')
} | Select-Object -First 1

if (-not $preferred) {
    $preferred = $assets | Where-Object { $_.name -match 'win' -and $_.name -match '\.zip$' } | Select-Object -First 1
}
if (-not $preferred) {
    Write-Err "Release nesatur Windows zip. Tag: $($release.tag_name)"
    Write-Host "Pieejamie asset:"
    $assets | ForEach-Object { Write-Host "  - $($_.name)" }
    exit 1
}

$zipPath = Join-Path $cache $preferred.name
Write-Host "Lejupielādē: $($preferred.browser_download_url)"
Invoke-WebRequest -Uri $preferred.browser_download_url -OutFile $zipPath -UseBasicParsing

$extract = Join-Path $cache ("extract-" + $release.tag_name)
if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
Expand-Archive -Path $zipPath -DestinationPath $extract -Force

# Atrod llama-server.exe
$server = Get-ChildItem -Path $extract -Recurse -Filter "llama-server.exe" | Select-Object -First 1
if (-not $server) {
    # vecāki buildi: server.exe
    $server = Get-ChildItem -Path $extract -Recurse -Filter "server.exe" | Select-Object -First 1
}
if (-not $server) {
    Write-Err "Arhīvā nav llama-server.exe"
    exit 1
}

# Kopē visu bināru mapi (DLL blakus)
$binDir = $server.Directory.FullName
Copy-Item -Path (Join-Path $binDir "*") -Destination $InstallDir -Recurse -Force
$finalExe = Join-Path $InstallDir "llama-server.exe"
if (-not (Test-Path $finalExe)) {
    Copy-Item $server.FullName $finalExe -Force
}

@{
    installed_at = (Get-Date).ToString("o")
    tag = $release.tag_name
    asset = $preferred.name
    exe = $finalExe
    primary = "llama.cpp"
} | ConvertTo-Json | Set-Content (Join-Path $InstallDir "install.json") -Encoding UTF8

Write-Ok "llama-server: $finalExe"
Write-Host "Palaišana: scripts\start_llama_server.ps1"
Write-Host "API: http://127.0.0.1:8080/v1"
