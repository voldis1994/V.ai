#Requires -Version 5.1
# Download llama.cpp llama-server for Windows x64 (PRIMARY Main Brain OS AI).
# NOTE: GitHub /releases/latest on this repo can point to a stub tag (v0.7.0)
# without binaries - we scan recent releases for win-cpu-x64.zip instead.
param(
    [switch]$AcceptDownloads,
    [string]$InstallDir = ""
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Write-Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Write-Warn($m) { Write-Host "[WARN] $m" -ForegroundColor Yellow }
function Write-Err($m) { Write-Host "[ERROR] $m" -ForegroundColor Red }

if (-not $InstallDir) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "MainBrainOS\llama"
}
$cache = Join-Path $env:LOCALAPPDATA "MainBrainOS\bootstrap-cache"
New-Item -ItemType Directory -Force -Path $InstallDir, $cache | Out-Null

Write-Step "llama.cpp llama-server install"
Write-Host "Target: $InstallDir"
Write-Host "PRIMARY AI path (Ollama NOT required)."

if (-not $AcceptDownloads) {
    $ans = Read-Host "Download llama-server from GitHub Releases? (Y/N)"
    if ($ans -notmatch '^[yYjJ]') { Write-Warn "Cancelled."; exit 0 }
}

$headers = @{ "User-Agent" = "MainBrainOS"; "Accept" = "application/vnd.github+json" }
$apiList = @(
    "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=30",
    "https://api.github.com/repos/ggerganov/llama.cpp/releases?per_page=30"
)

function Select-WinCpuAsset($assets) {
    $list = @($assets)
    # Best: official CPU x64 build
    $a = $list | Where-Object { $_.name -match 'llama-b\d+-bin-win-cpu-x64\.zip$' } | Select-Object -First 1
    if ($a) { return $a }
    $a = $list | Where-Object {
        $_.name -match 'win' -and $_.name -match '\.zip$' -and $_.name -match 'cpu' -and $_.name -match 'x64' -and ($_.name -notmatch 'arm')
    } | Select-Object -First 1
    if ($a) { return $a }
    $a = $list | Where-Object {
        $_.name -match 'win' -and $_.name -match '\.zip$' -and $_.name -match 'avx2' -and ($_.name -notmatch 'cuda')
    } | Select-Object -First 1
    if ($a) { return $a }
    return ($list | Where-Object {
        $_.name -match 'win' -and $_.name -match '\.zip$' -and ($_.name -notmatch 'cuda') -and ($_.name -notmatch 'arm')
    } | Select-Object -First 1)
}

$chosenRelease = $null
$preferred = $null
foreach ($api in $apiList) {
    try {
        Write-Host "Query: $api"
        $releases = Invoke-RestMethod -Uri $api -Headers $headers
        foreach ($rel in @($releases)) {
            $asset = Select-WinCpuAsset $rel.assets
            if ($asset) {
                $chosenRelease = $rel
                $preferred = $asset
                break
            }
        }
        if ($preferred) { break }
    } catch {
        Write-Warn "Failed: $_"
    }
}

if (-not $preferred) {
    Write-Err "No Windows llama-server zip found in recent releases."
    Write-Host "Manual: https://github.com/ggml-org/llama.cpp/releases"
    Write-Host "Download llama-bXXXX-bin-win-cpu-x64.zip and extract llama-server.exe to:"
    Write-Host "  $InstallDir"
    exit 1
}

Write-Ok "Release: $($chosenRelease.tag_name) / $($preferred.name)"

$zipPath = Join-Path $cache $preferred.name
Write-Host "Downloading: $($preferred.browser_download_url)"
Invoke-WebRequest -Uri $preferred.browser_download_url -OutFile $zipPath -UseBasicParsing

$safeTag = ($chosenRelease.tag_name -replace '[^\w\.-]', '_')
$extract = Join-Path $cache ("extract-" + $safeTag)
if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
Expand-Archive -Path $zipPath -DestinationPath $extract -Force

$server = Get-ChildItem -Path $extract -Recurse -Filter "llama-server.exe" | Select-Object -First 1
if (-not $server) {
    $server = Get-ChildItem -Path $extract -Recurse -Filter "server.exe" | Select-Object -First 1
}
if (-not $server) {
    Write-Err "Archive has no llama-server.exe"
    exit 1
}

$binDir = $server.Directory.FullName
Copy-Item -Path (Join-Path $binDir "*") -Destination $InstallDir -Recurse -Force
$finalExe = Join-Path $InstallDir "llama-server.exe"
if (-not (Test-Path $finalExe)) {
    Copy-Item $server.FullName $finalExe -Force
}
if (-not (Test-Path $finalExe)) {
    Write-Err "Failed to place llama-server.exe in $InstallDir"
    exit 1
}

@{
    installed_at = (Get-Date).ToString("o")
    tag = $chosenRelease.tag_name
    asset = $preferred.name
    exe = $finalExe
    primary = "llama.cpp"
} | ConvertTo-Json | Set-Content (Join-Path $InstallDir "install.json") -Encoding UTF8

Write-Ok "llama-server: $finalExe"
Write-Host "Start: scripts\start_llama_server.ps1"
Write-Host "API: http://127.0.0.1:8080/v1"
exit 0
