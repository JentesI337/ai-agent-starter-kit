param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$RequiredPythonVersion = '3.12'

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

$rootDir = $PSScriptRoot
$backendDir = Join-Path $rootDir 'backend'

Write-Step "Preparing backend test environment"
Set-Location $backendDir

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python launcher 'py' not found. Install Python 3.12 and rerun."
}

try {
    & py -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" | Out-Null
}
catch {
    throw "Python 3.12 is required. Install it (e.g. winget install --id Python.Python.3.12 -e) and rerun."
}

$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'
$recreateVenv = $false
if (Test-Path $venvPython) {
    $venvVersion = (& $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
    if ($venvVersion -ne $RequiredPythonVersion) {
        Write-Step "Recreating backend/.venv (found Python $venvVersion, expected $RequiredPythonVersion)"
        Remove-Item -Recurse -Force '.venv'
        $recreateVenv = $true
    }
}

if (-not (Test-Path '.venv') -or $recreateVenv) {
    & py -3.12 -m venv .venv
}

$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'

if (-not $SkipInstall) {
    Write-Step "Installing backend + test dependencies"
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt -r requirements-test.txt
}

Write-Step "Running backend end-to-end tests"
$env:OLLAMA_BIN = 'python'
& $venvPython -m pytest tests -q
