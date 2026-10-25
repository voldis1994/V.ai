#Requires -Version 5.1
<#
.SYNOPSIS
  Lejupielādē GGUF modeļus Main Brain OS lomām ar skaidru lietotāja apstiprinājumu.
#>
param(
    [ValidateSet("light", "standard")]
    [string]$Profile = "light",
    [switch]$AcceptDownloads,
    [switch]$Force,
    [string]$ModelsDir = ""
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Write-Ok($m) { Write-Host "[OK] $m" -ForegroundColor Green }
function Write-Warn($m) { Write-Host "[BRĪDINĀJUMS] $m" -ForegroundColor Yellow }
function Write-Err($m) { Write-Host "[KĻŪDA] $m" -ForegroundColor Red }

$root = if ($PSScriptRoot) { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path } else { (Get-Location).Path }
$manifestPath = Join-Path $root "models\manifest.json"
if (-not (Test-Path $manifestPath)) {
    Write-Err "Nav atrasts models\manifest.json"
    exit 1
}

$manifest = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $ModelsDir) {
    $ModelsDir = Join-Path $env:LOCALAPPDATA "MainBrainOS\models"
}
New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null

$profileInfo = $manifest.profiles.$Profile
if (-not $profileInfo) {
    Write-Err "Nezināms profils: $Profile"
    exit 1
}

$modelIds = @($profileInfo.models)
$totalMb = 0
$plan = @()
foreach ($id in $modelIds) {
    $m = $manifest.models.$id
    if (-not $m) { Write-Err "Manifestā nav modeļa: $id"; exit 1 }
    $totalMb += [int]$m.approx_mb
    $plan += [pscustomobject]@{
        Id = $id
        Role = $m.role
        Filename = $m.filename
        Url = $m.url
        ApproxMb = [int]$m.approx_mb
        License = $m.license
        SourcePage = $m.source_page
        Dest = Join-Path $ModelsDir $m.filename
    }
}

Write-Step "GGUF modeļu lejupielāde ($Profile)"
Write-Host "Mērķa mape: $ModelsDir"
Write-Host "Aptuvenais izmērs: ~$([math]::Round($totalMb/1024, 2)) GB ($totalMb MB)"
Write-Host ""
Write-Host "Modeļi:"
foreach ($p in $plan) {
    Write-Host ("  - [{0}] {1} (~{2} MB)  licence: {3}" -f $p.Role, $p.Filename, $p.ApproxMb, $p.License)
    Write-Host ("    avots: {0}" -f $p.SourcePage)
}

# Disk space check (Get-PSDrive wants "C", not "C:")
$needGb = [math]::Round(($totalMb * 1.15) / 1024, 2)
try {
    $driveName = (Get-Item $ModelsDir).PSDrive.Name
    if (-not $driveName) { $driveName = "C" }
    $freeGb = [math]::Round((Get-PSDrive -Name $driveName).Free / 1GB, 2)
    Write-Host ""
    Write-Host "Free space on ${driveName}: $freeGb GB (need ~$needGb GB)"
    if ($freeGb -lt $needGb) {
        Write-Err "Not enough disk space."
        exit 1
    }
} catch {
    Write-Warn "Could not check free disk space: $_ (continuing)"
}

if (-not $AcceptDownloads) {
    Write-Host ""
    Write-Host "Uzmanību: faili ir lieli un tiek lejupielādēti no Hugging Face." -ForegroundColor Yellow
    Write-Host "Pārliecinieties, ka piekrītat katra modeļa licencei (skatīt source_page)."
    $ans = Read-Host "Lejupielādēt šo komplektu tagad? (J/N)"
    if ($ans -notmatch '^[jJyY]') {
        Write-Warn "Modeļu lejupielāde atcelta."
        exit 0
    }
}

function Download-File($Url, $Dest) {
    # BitsTransfer ir stabilāks lieliem failiem; fallback uz WebClient
    Write-Host "Lejupielādē -> $Dest"
    try {
        Import-Module BitsTransfer -ErrorAction Stop
        Start-BitsTransfer -Source $Url -Destination $Dest -DisplayName "MainBrainOS-GGUF" -Description (Split-Path $Dest -Leaf)
        return
    } catch {
        Write-Warn "BITS nav pieejams, izmanto WebClient: $_"
    }
    $wc = New-Object System.Net.WebClient
    $wc.Headers.Add("User-Agent", "MainBrainOS-Bootstrap/1.0")
    $wc.DownloadFile($Url, $Dest)
}

$downloaded = @()
foreach ($p in $plan) {
    Write-Step "$($p.Role): $($p.Filename)"
    if ((Test-Path $p.Dest) -and -not $Force) {
        $size = (Get-Item $p.Dest).Length
        if ($size -gt 1MB) {
            Write-Ok "Jau ir lokāli ($([math]::Round($size/1MB)) MB) - izlaiž"
            $downloaded += $p
            continue
        }
    }
    $partial = "$($p.Dest).partial"
    try {
        Download-File -Url $p.Url -Dest $partial
        if (-not (Test-Path $partial) -or (Get-Item $partial).Length -lt 1MB) {
            throw "Lejupielāde pārāk maza vai tukša"
        }
        Move-Item -Force $partial $p.Dest
        $hash = (Get-FileHash -Algorithm SHA256 -Path $p.Dest).Hash
        Write-Ok "Saglabāts. SHA256=$hash"
        $downloaded += $p
        # metadata blakus
        @{
            id = $p.Id
            role = $p.Role
            filename = $p.Filename
            url = $p.Url
            license = $p.License
            source_page = $p.SourcePage
            sha256 = $hash
            downloaded_at = (Get-Date).ToString("o")
        } | ConvertTo-Json | Set-Content ($p.Dest + ".json") -Encoding UTF8
    } catch {
        Write-Err "Neizdevās lejupielādēt $($p.Filename): $_"
        if (Test-Path $partial) { Remove-Item $partial -Force -ErrorAction SilentlyContinue }
        Write-Host "Manuāli: $($p.SourcePage)"
    }
}

# role map for Main Brain
$roleMap = @{}
foreach ($p in $downloaded) {
    if (Test-Path $p.Dest) {
        $roleMap[$p.Role] = $p.Dest
    }
}
$roleMap | ConvertTo-Json | Set-Content (Join-Path $ModelsDir "roles.json") -Encoding UTF8

# also symlink/copy hint into repo models/ if writable
$repoModels = Join-Path $root "models"
try {
    Copy-Item (Join-Path $ModelsDir "roles.json") (Join-Path $repoModels "roles.json") -Force -ErrorAction SilentlyContinue
} catch {}

Write-Step "Rezultāts"
Write-Host "Modeļi: $ModelsDir"
Write-Host "Lomu karte: $(Join-Path $ModelsDir 'roles.json')"
Write-Host ""
Write-Host "Nākamais solis (PRIMĀRI llama.cpp, ne Ollama):"
Write-Host "  scripts\install_llama_server.ps1"
Write-Host "  scripts\start_llama_server.ps1"
Write-Host "API: http://127.0.0.1:8080/v1"
Write-Ok "Modeļu lejupielāde pabeigta (vai daļēji - skatiet brīdinājumus)"
