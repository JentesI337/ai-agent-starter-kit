param(
    [string]$BaseUrl = 'http://127.0.0.1:8000',
    [string]$Levels = 'easy,mid,hard',
    [int]$RunsPerCase = 1,
    [string]$ScenarioFile = '',
    [string]$Model = '',
    [switch]$SkipInstall,
    [switch]$NoAutoStartBackend,
    [switch]$NoFailOnError
)

$ErrorActionPreference = 'Stop'
$RequiredPythonVersion = '3.12'

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Test-BackendHealth([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri "$Url/api/runtime/status" -TimeoutSec 3 -UseBasicParsing
        return ($response.StatusCode -eq 200)
    }
    catch {
        return $false
    }
}

$rootDir = $PSScriptRoot
$backendDir = Join-Path $rootDir 'backend'
$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'

Write-Step "Preparing backend benchmark environment"
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
    Write-Step "Installing backend dependencies"
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
}

$backendStartedHere = $false
$backendProcess = $null

try {
    $backendHealthy = Test-BackendHealth $BaseUrl

    if (-not $backendHealthy) {
        if ($NoAutoStartBackend) {
            throw "Backend is not reachable at $BaseUrl and auto-start is disabled."
        }

        $baseUri = [Uri]$BaseUrl
        $host = $baseUri.Host
        $port = if ($baseUri.IsDefaultPort) {
            if ($baseUri.Scheme -eq 'https') { 443 } else { 80 }
        }
        else {
            $baseUri.Port
        }

        Write-Step "Starting backend server at $host`:$port"
        $backendProcess = Start-Process -FilePath $venvPython -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', $host, '--port', "$port" -WorkingDirectory $backendDir -PassThru
        $backendStartedHere = $true

        $deadline = (Get-Date).AddSeconds(30)
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Milliseconds 500
            if (Test-BackendHealth $BaseUrl) {
                $backendHealthy = $true
                break
            }
        }

        if (-not $backendHealthy) {
            throw "Backend did not become healthy at $BaseUrl within 30 seconds."
        }
    }

    Write-Step "Running benchmark suite (levels=$Levels runsPerCase=$RunsPerCase)"

    $argsList = @(
        'benchmarks/run_benchmark.py',
        '--base-url', $BaseUrl,
        '--levels', $Levels,
        '--runs-per-case', "$RunsPerCase"
    )

    if ($Model) {
        $argsList += @('--model', $Model)
    }

    if ($ScenarioFile) {
        $argsList += @('--scenario-file', $ScenarioFile)
    }

    if ($NoFailOnError) {
        $argsList += '--no-fail-on-error'
    }

    & $venvPython @argsList
    exit $LASTEXITCODE
}
finally {
    if ($backendStartedHere -and $backendProcess -and -not $backendProcess.HasExited) {
        Write-Step "Stopping backend server started by benchmark script"
        Stop-Process -Id $backendProcess.Id -Force
    }
}
