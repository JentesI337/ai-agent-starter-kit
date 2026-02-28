param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

$rootDir = $PSScriptRoot
$backendDir = Join-Path $rootDir 'backend'

Write-Step "Preparing backend test environment"
Set-Location $backendDir

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python not found. Install Python 3.11+ and rerun."
}

if (-not (Test-Path '.venv')) {
    python -m venv .venv
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
