param(
    [int]$LlmPort = 11434,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 4200,
    [ValidateSet('local', 'api', '')]
    [string]$RuntimeMode = ''
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Resolve-RuntimeMode {
    if ($RuntimeMode -in @('local', 'api')) {
        return $RuntimeMode
    }

    Write-Host "Select runtime mode:" -ForegroundColor Cyan
    Write-Host "1) local (70B)"
    Write-Host "2) api (qwen2.5:7b-instruct)"
    $choice = Read-Host "Enter 1 or 2"
    if ($choice -eq '2') {
        return 'api'
    }
    return 'local'
}

function Warn-RootVenvConflict {
    $rootVenv = Join-Path $PSScriptRoot '.venv'
    $backendVenv = Join-Path $PSScriptRoot 'backend\.venv'
    if ((Test-Path $rootVenv) -and ($rootVenv -ne $backendVenv)) {
        Write-Host "Warning: Found root .venv at $rootVenv. Startup uses backend/.venv only." -ForegroundColor Yellow
    }
}

function Test-TcpPort([string]$HostName, [int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(700)
        if (-not $ok) {
            $client.Close()
            return $false
        }
        $client.EndConnect($iar) | Out-Null
        $client.Close()
        return $true
    }
    catch {
        return $false
    }
}

function Ensure-Port-Free([int]$Port, [string]$ServiceName) {
    if (Test-TcpPort -HostName '127.0.0.1' -Port $Port) {
        throw "Port conflict: $ServiceName cannot start because port $Port is already in use. Please choose another port."
    }
}

function Ensure-Ollama-Endpoint([int]$Port) {
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/tags" -Method Get -TimeoutSec 3 | Out-Null
    }
    catch {
        throw "Port $Port is open but Ollama API is not responding there. Adjust -LlmPort and rerun."
    }
}

function Ensure-Command([string]$Name, [string]$InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name not found. $InstallHint"
    }
}

function Get-OllamaBinaryPath {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'),
        'C:\Program Files\Ollama\ollama.exe'
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Ensure-Python {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return
    }

    Write-Step "Python not found, trying install via winget"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    }

    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python install failed. Please install Python 3.11+ and rerun script."
    }
}

function Ensure-Node {
    if ((Get-Command node -ErrorAction SilentlyContinue) -and (Get-Command npm -ErrorAction SilentlyContinue)) {
        return
    }

    Write-Step "Node.js/npm not found, trying install via winget"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id OpenJS.NodeJS.LTS -e --accept-package-agreements --accept-source-agreements
    }

    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Node.js install failed. Please install Node.js LTS and rerun script."
    }
}

function Ensure-Ollama {
    $ollamaPath = Get-OllamaBinaryPath
    if (-not $ollamaPath) {
        Write-Step "Ollama not found, trying install via winget"
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install --id Ollama.Ollama -e --accept-package-agreements --accept-source-agreements
        }
        Start-Sleep -Seconds 2
        $ollamaPath = Get-OllamaBinaryPath
    }

    if (-not $ollamaPath) {
        throw "Ollama install failed. Install from https://ollama.com and rerun script."
    }

    return $ollamaPath
}

function Ensure-Ollama-Running([int]$Port) {
    $ollamaPath = Ensure-Ollama
    if (Test-TcpPort -HostName '127.0.0.1' -Port $Port) {
        Ensure-Ollama-Endpoint -Port $Port
        Write-Host "Ollama already running on port $Port"
        return $ollamaPath
    }

    Write-Step "Starting Ollama on port $Port"
    $env:OLLAMA_HOST = "127.0.0.1:$Port"
    Start-Process -FilePath $ollamaPath -ArgumentList "serve" -WindowStyle Minimized | Out-Null

    for ($i = 0; $i -lt 15; $i++) {
        Start-Sleep -Seconds 1
        if (Test-TcpPort -HostName '127.0.0.1' -Port $Port) {
            Ensure-Ollama-Endpoint -Port $Port
            Write-Host "Ollama started on port $Port"
            return $ollamaPath
        }
    }

    throw "Ollama did not start on port $Port"
}

function Ensure-BackendEnv([int]$Port) {
    $backendDir = Join-Path $PSScriptRoot 'backend'
    $envFile = Join-Path $backendDir '.env'
    $envExample = Join-Path $backendDir '.env.example'

    if (-not (Test-Path $envFile)) {
        Copy-Item $envExample $envFile
    }

    $lines = Get-Content $envFile
    $updated = @()
    $found = $false

    foreach ($line in $lines) {
        if ($line -match '^LLM_BASE_URL=') {
            $updated += "LLM_BASE_URL=http://localhost:$Port/v1"
            $found = $true
        }
        else {
            $updated += $line
        }
    }

    if (-not $found) {
        $updated += "LLM_BASE_URL=http://localhost:$Port/v1"
    }

    Set-Content -Path $envFile -Value $updated -Encoding UTF8
}

function Upsert-EnvVar([string]$FilePath, [string]$Name, [string]$Value) {
    $lines = @()
    if (Test-Path $FilePath) {
        $lines = Get-Content $FilePath
    }

    $updated = @()
    $found = $false
    foreach ($line in $lines) {
        if ($line -match "^$Name=") {
            $updated += "$Name=$Value"
            $found = $true
        }
        else {
            $updated += $line
        }
    }

    if (-not $found) {
        $updated += "$Name=$Value"
    }

    Set-Content -Path $FilePath -Value $updated -Encoding UTF8
}

function Set-RuntimeState([string]$Mode, [int]$Port) {
    $backendDir = Join-Path $PSScriptRoot 'backend'
    $envFile = Join-Path $backendDir '.env'
    $stateFile = Join-Path $backendDir 'runtime_state.json'
    $envVars = @{}

    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^\s*#' -or -not $line.Contains('=')) {
                continue
            }
            $parts = $line.Split('=', 2)
            $envVars[$parts[0].Trim()] = $parts[1].Trim()
        }
    }

    $localModel = if ($envVars.ContainsKey('LOCAL_MODEL')) { $envVars['LOCAL_MODEL'] } else { 'llama3.3:70b-instruct-q4_K_M' }
    $apiModel = if ($envVars.ContainsKey('API_MODEL')) { $envVars['API_MODEL'] } else { 'qwen2.5:7b-instruct' }
    $apiBaseUrl = if ($envVars.ContainsKey('API_BASE_URL')) { $envVars['API_BASE_URL'] } else { "http://localhost:$Port/v1" }
    $llmBaseUrl = if ($envVars.ContainsKey('LLM_BASE_URL')) { $envVars['LLM_BASE_URL'] } else { "http://localhost:$Port/v1" }
    $apiKey = if ($envVars.ContainsKey('LLAMA_API_KEY')) { $envVars['LLAMA_API_KEY'] } elseif ($envVars.ContainsKey('LLM_API_KEY')) { $envVars['LLM_API_KEY'] } else { '' }

    if ($Mode -eq 'api') {
        $state = @{
            runtime = 'api'
            base_url = $apiBaseUrl
            model = $apiModel
            api_key = $apiKey
        }
    }
    else {
        $state = @{
            runtime = 'local'
            base_url = $llmBaseUrl
            model = $localModel
            api_key = if ($envVars.ContainsKey('LLM_API_KEY')) { $envVars['LLM_API_KEY'] } else { 'not-needed' }
        }
    }

    $state | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8
}

Write-Step "Selecting runtime"
$selectedRuntime = Resolve-RuntimeMode
Write-Host "Selected runtime: $selectedRuntime"
Write-Step "Checking Ollama"
Warn-RootVenvConflict
$ollamaBinary = Ensure-Ollama

if ($selectedRuntime -eq 'local') {
    $ollamaBinary = Ensure-Ollama-Running -Port $LlmPort
}
else {
    Write-Step "API runtime selected - using local Ollama gateway with API model"
}

Write-Step "Installing backend (python + deps)"
Ensure-Python
$backendDir = Join-Path $PSScriptRoot 'backend'
Ensure-BackendEnv -Port $LlmPort
Upsert-EnvVar -FilePath (Join-Path $backendDir '.env') -Name 'OLLAMA_BIN' -Value $ollamaBinary
Set-RuntimeState -Mode $selectedRuntime -Port $LlmPort
Set-Location $backendDir

if (-not (Test-Path '.venv')) {
    python -m venv .venv
}

$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Step "Running backend"
Ensure-Port-Free -Port $BackendPort -ServiceName 'backend'
Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port $BackendPort" -WorkingDirectory $backendDir -WindowStyle Minimized | Out-Null

Write-Step "Installing frontend (node + deps)"
Ensure-Node
$frontendDir = Join-Path $PSScriptRoot 'frontend'
Set-Location $frontendDir
npm install

Write-Step "Building frontend"
npm run build

Write-Step "Running frontend"
Ensure-Port-Free -Port $FrontendPort -ServiceName 'frontend'
npm start -- --port $FrontendPort
