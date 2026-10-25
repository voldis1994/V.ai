#Requires -Version 5.1
# Shared helper: find Python 3.12 or 3.13 only (NOT 3.14+).
# Dot-source: . "$PSScriptRoot\Find-Python.ps1"

function Get-PythonVersionString {
    param([string]$Exe, [string[]]$PrefixArgs = @())
    try {
        $out = & $Exe @PrefixArgs "--version" 2>&1 | Out-String
        if ($out -match 'Python\s+(3\.\d+\.\d+)') { return $Matches[1] }
    } catch {}
    return $null
}

function Test-SupportedPythonVersion {
    param([string]$Version)
    if (-not $Version) { return $false }
    if ($Version -match '^3\.12\.') { return $true }
    if ($Version -match '^3\.13\.') { return $true }
    return $false
}

function Find-SupportedPython {
    # Returns hashtable: Exe, Args (array), Version, Display
    $candidates = @()

    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($tag in @("-3.12", "-3.13")) {
            try {
                $ver = & py $tag --version 2>&1 | Out-String
                if ($ver -match 'Python\s+(3\.\d+\.\d+)') {
                    $v = $Matches[1]
                    if (Test-SupportedPythonVersion $v) {
                        $candidates += @{ Exe = "py"; Args = @($tag); Version = $v }
                    }
                }
            } catch {}
        }
    }

    foreach ($name in @("python3.12", "python3.13", "python12", "python")) {
        if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { continue }
        $v = Get-PythonVersionString $name
        if (Test-SupportedPythonVersion $v) {
            $candidates += @{ Exe = $name; Args = @(); Version = $v }
        }
    }

    # Common install locations
    $pf = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python313\python.exe",
        "${env:ProgramFiles(x86)}\Python312-32\python.exe"
    )
    foreach ($p in $pf) {
        if (Test-Path $p) {
            $v = Get-PythonVersionString $p
            if (Test-SupportedPythonVersion $v) {
                $candidates += @{ Exe = $p; Args = @(); Version = $v }
            }
        }
    }

    if ($candidates.Count -eq 0) { return $null }
    # Prefer 3.12
    $pref = $candidates | Where-Object { $_.Version -like '3.12.*' } | Select-Object -First 1
    if ($pref) { return $pref }
    return $candidates[0]
}

function Install-Python312 {
    param([string]$CacheDir)
    New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "Installing Python 3.12 via winget..."
        winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements --disable-interactivity
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("PATH", "User")
    }
    $found = Find-SupportedPython
    if ($found) { return $found }

    $installer = Join-Path $CacheDir "python-3.12.8-amd64.exe"
    Write-Host "Downloading Python 3.12.8..."
    Invoke-WebRequest -Uri "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe" -OutFile $installer -UseBasicParsing
    Write-Host "Installing Python 3.12 (per-user, add to PATH)..."
    Start-Process -FilePath $installer -ArgumentList "/quiet","InstallAllUsers=0","PrependPath=1","Include_test=0","Include_pip=1" -Wait
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("PATH", "User")
    Start-Sleep -Seconds 2
    return (Find-SupportedPython)
}
