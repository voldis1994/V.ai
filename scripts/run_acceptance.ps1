#Requires -Version 5.1
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$report = @()
function Add-Result($Id, $Status, $Evidence) {
    $script:report += [pscustomobject]@{ Id = $Id; Status = $Status; Evidence = $Evidence }
    Write-Host "[$Status] $Id - $Evidence"
}

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "=== Pieņemšanas testi ==="
& $py -m pytest -q tests/python
if ($LASTEXITCODE -eq 0) {
    Add-Result "A-F-G-H-L-python" "TESTĒTS" "pytest tests/python OK"
} else {
    Add-Result "A-F-G-H-L-python" "NESTRĀDĀ" "pytest kļūda"
}

dotnet build (Join-Path $root "src\desktop\MainBrain.Contracts\MainBrain.Contracts.csproj") -c Release
if ($LASTEXITCODE -eq 0) {
    Add-Result "contracts-build" "TESTĒTS" "MainBrain.Contracts OK"
} else {
    Add-Result "contracts-build" "NESTRĀDĀ" "Contracts būvēšana neizdevās"
}

dotnet build (Join-Path $root "src\desktop\MainBrain.Desktop\MainBrain.Desktop.csproj") -c Release
if ($LASTEXITCODE -eq 0) {
    Add-Result "M-desktop-build" "TESTĒTS" "MainBrain.exe projekts kompilējas"
} else {
    Add-Result "M-desktop-build" "BLOĶĒTS" "WPF būvēšana prasa Windows + workload"
}

$report | ConvertTo-Json | Set-Content (Join-Path $root "docs\acceptance_last_run.json") -Encoding UTF8
Write-Host "Skatīt docs/TEST_REPORT.md un docs/BUILD_STATUS.md"
