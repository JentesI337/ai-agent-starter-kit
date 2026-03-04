param(
    [int]$LlmPort = 11434,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 4200,
    [ValidateSet('local', 'api', '')]
    [string]$RuntimeMode = '',
    [ValidateSet('', 'minimax-m2:cloud', 'gpt-oss:20b-cloud', 'qwen3-coder:480b-cloud')]
    [string]$ApiModel = '',
    [ValidateSet('', 'true', 'false')]
    [string]$LongTermMemoryEnabled = '',
    [ValidateSet('', 'true', 'false')]
    [string]$SessionDistillationEnabled = '',
    [ValidateSet('', 'true', 'false')]
    [string]$FailureJournalEnabled = '',
    [string]$LongTermMemoryDbPath = ''
)

$ErrorActionPreference = 'Stop'
$SupportedApiModels = @('minimax-m2:cloud', 'gpt-oss:20b-cloud', 'qwen3-coder:480b-cloud')

$cleanupScript = Join-Path $PSScriptRoot 'clean-dev.ps1'
if (Test-Path $cleanupScript) {
    Write-Host "`n==> Cleaning stale dev processes" -ForegroundColor Cyan
    & $cleanupScript -LlmPort $LlmPort -BackendPort $BackendPort -FrontendPort $FrontendPort
}

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

function Resolve-RuntimeMode {
    if ($RuntimeMode -in @('local', 'api')) {
        return $RuntimeMode
    }

    Write-Host "Select runtime mode:" -ForegroundColor Cyan
    Write-Host "1) local (70B)"
    Write-Host "2) api (cloud model selection)"
    $choice = Read-Host "Enter 1 or 2"
    if ($choice -eq '2') {
        return 'api'
    }
    return 'local'
}

function Resolve-ApiModel([string]$CurrentApiModel) {
    if ($ApiModel -and ($ApiModel -in $SupportedApiModels)) {
        return $ApiModel
    }

    $defaultModel = if ($CurrentApiModel -in $SupportedApiModels) { $CurrentApiModel } else { 'minimax-m2:cloud' }

    Write-Host "Select API model:" -ForegroundColor Cyan
    Write-Host "1) minimax-m2:cloud (small - very low cost)"
    Write-Host "2) gpt-oss:20b-cloud (mid - mid cost)"
    Write-Host "3) qwen3-coder:480b-cloud (high - high cost)"
    Write-Host "Press Enter for default: $defaultModel"

    $choice = Read-Host "Enter 1, 2 or 3"
    switch ($choice) {
        '1' { return 'minimax-m2:cloud' }
        '2' { return 'gpt-oss:20b-cloud' }
        '3' { return 'qwen3-coder:480b-cloud' }
        '' { return $defaultModel }
        default {
            Write-Host "Invalid choice. Using default: $defaultModel" -ForegroundColor Yellow
            return $defaultModel
        }
    }
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
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            & py -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" | Out-Null
            return
        }
        catch {
        }
    }

    Write-Step "Python 3.12 not found, trying install via winget"
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            & py -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" | Out-Null
            return
        }
        catch {
        }
    }

    throw "Python 3.12 install failed. Please install Python 3.12 and rerun script."
}

function Ensure-BackendVenv312([string]$BackendDirPath) {
    $venvDir = Join-Path $BackendDirPath '.venv'
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'

    if (Test-Path $venvPython) {
        $version = (& $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
        if ($version -ne '3.12') {
            Write-Step "Recreating backend/.venv (found Python $version, expected 3.12)"
            Remove-Item -Recurse -Force $venvDir
        }
    }

    if (-not (Test-Path $venvDir)) {
        & py -3.12 -m venv $venvDir
    }

    return (Join-Path $venvDir 'Scripts\python.exe')
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

function Ensure-CloudLogin([string]$OllamaBin, [string]$ModelName) {
    if (-not $ModelName.ToLower().EndsWith(':cloud')) {
        return
    }

    Write-Step "Checking Ollama Cloud login"
    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    try {
        $proc = Start-Process -FilePath $OllamaBin -ArgumentList 'whoami' -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        $raw = ""
        if (Test-Path $stdoutFile) {
            $raw += (Get-Content $stdoutFile -Raw)
        }
        if (Test-Path $stderrFile) {
            $raw += (Get-Content $stderrFile -Raw)
        }

        if ($proc.ExitCode -ne 0) {
            if ($raw -match 'unknown command') {
                Write-Host "Ollama version has no 'whoami'; running 'ollama signin' to ensure cloud login." -ForegroundColor Yellow
                & $OllamaBin signin
                if ($LASTEXITCODE -ne 0) {
                    throw "Cloud login failed. Complete 'ollama signin' successfully and rerun start-dev."
                }
                return
            }

            Write-Host "Cloud login missing. Running 'ollama signin'..." -ForegroundColor Yellow
            & $OllamaBin signin
            if ($LASTEXITCODE -ne 0) {
                throw "Cloud login failed. Complete 'ollama signin' successfully and rerun start-dev."
            }
        }
    }
    finally {
        Remove-Item $stdoutFile -ErrorAction SilentlyContinue
        Remove-Item $stderrFile -ErrorAction SilentlyContinue
    }
}

function Invoke-PipInstall([string]$PythonExe, [string[]]$Arguments, [string]$StepName) {
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        Write-Host "Pip step '$StepName' (attempt $attempt/3)"
        & $PythonExe -m pip --disable-pip-version-check --no-input @Arguments
        if ($LASTEXITCODE -eq 0) {
            return
        }

        if ($attempt -lt 3) {
            Start-Sleep -Seconds 2
        }
    }

    throw "Backend dependency install failed during '$StepName'. If you see 'Operation cancelled by user', rerun after checking network/proxy and Python permissions."
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

function Get-EnvOrDefault([string]$FilePath, [string]$Name, [string]$DefaultValue) {
    if (-not (Test-Path $FilePath)) {
        return $DefaultValue
    }

    foreach ($line in Get-Content $FilePath) {
        if ($line -match "^$Name=(.*)$") {
            $value = $Matches[1].Trim()
            if ($value) {
                return $value
            }
        }
    }

    return $DefaultValue
}

function Resolve-BoolEnvValue([string]$RequestedValue, [string]$CurrentValue, [string]$DefaultValue = 'true') {
    $requested = ($RequestedValue ?? '').Trim().ToLowerInvariant()
    if ($requested -in @('true', 'false')) {
        return $requested
    }

    $current = ($CurrentValue ?? '').Trim().ToLowerInvariant()
    if ($current -in @('true', 'false')) {
        return $current
    }

    return $DefaultValue
}

function Test-ModelInstalled([string]$OllamaBin, [string]$ModelName) {
    $listOutput = & $OllamaBin list 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $false
    }
    return ($listOutput -match [regex]::Escape($ModelName))
}

function Ensure-SelectedModelInstalled([string]$OllamaBin, [string]$ModelName, [string]$RuntimeMode) {
    Write-Step "Ensuring model is installed: $ModelName"

    if (Test-ModelInstalled -OllamaBin $OllamaBin -ModelName $ModelName) {
        Write-Host "Model already installed: $ModelName"
        return
    }

    Write-Host "Model not found locally. Pulling: $ModelName"
    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    try {
        $proc = Start-Process -FilePath $OllamaBin -ArgumentList @('pull', $ModelName) -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        $raw = ""
        if (Test-Path $stdoutFile) {
            $raw += (Get-Content $stdoutFile -Raw)
        }
        if (Test-Path $stderrFile) {
            $raw += (Get-Content $stderrFile -Raw)
        }

        if ($raw) {
            Write-Host $raw.Trim()
        }

        if ($proc.ExitCode -ne 0) {
            $low = $raw.ToLowerInvariant()
            if ($low -match 'file does not exist' -or $low -match 'not found') {
                if ($RuntimeMode -eq 'api') {
                    throw "API model '$ModelName' is currently not available from this Ollama registry/version. You are logged in, but the model ID is not resolvable. Verify the exact cloud model name for your account and update API_MODEL."
                }
                throw "Local model '$ModelName' is not available in the configured Ollama registry. Verify model name and rerun start-dev."
            }

            if ($RuntimeMode -eq 'api') {
                throw "Could not install API model '$ModelName'. Cloud login may be missing or the model may be unavailable. Check ollama signin status and model identifier, then rerun start-dev."
            }
            throw "Could not install local model '$ModelName'. Check model name/network and rerun start-dev."
        }
    }
    finally {
        Remove-Item $stdoutFile -ErrorAction SilentlyContinue
        Remove-Item $stderrFile -ErrorAction SilentlyContinue
    }

}

function Ensure-SelectedModelRunnable([string]$Port, [string]$ModelName, [string]$RuntimeMode) {
    Write-Step "Validating model execution: $ModelName"
    try {
        $payload = @{
            model = $ModelName
            prompt = "ping"
            stream = $false
        } | ConvertTo-Json

        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/generate" -Method Post -ContentType 'application/json' -Body $payload -TimeoutSec 240
        Write-Host "Model is runnable: $ModelName"
    }
    catch {
        if ($RuntimeMode -eq 'api') {
            throw "API model '$ModelName' is not runnable. Ensure you're logged in via 'ollama signin' and have an active Pro plan. Details: $($_.Exception.Message)"
        }
        throw "Local model '$ModelName' is not runnable. Details: $($_.Exception.Message)"
    }
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
    $apiModel = if ($envVars.ContainsKey('API_MODEL')) { $envVars['API_MODEL'] } else { 'minimax-m2:cloud' }
    $apiBaseUrl = if ($envVars.ContainsKey('API_BASE_URL')) { $envVars['API_BASE_URL'] } else { "http://localhost:$Port/api" }
    $llmBaseUrl = if ($envVars.ContainsKey('LLM_BASE_URL')) { $envVars['LLM_BASE_URL'] } else { "http://localhost:$Port/v1" }

    if ($Mode -eq 'api') {
        $state = @{
            runtime = 'api'
            base_url = $apiBaseUrl
            model = $apiModel
        }
    }
    else {
        $state = @{
            runtime = 'local'
            base_url = $llmBaseUrl
            model = $localModel
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
    Write-Step "API runtime selected - using local Ollama API with selected cloud model"
    $ollamaBinary = Ensure-Ollama-Running -Port $LlmPort
}

Write-Step "Installing backend (python + deps)"
Ensure-Python
$backendDir = Join-Path $PSScriptRoot 'backend'
$envFilePath = Join-Path $backendDir '.env'
Ensure-BackendEnv -Port $LlmPort
Upsert-EnvVar -FilePath $envFilePath -Name 'OLLAMA_BIN' -Value $ollamaBinary

$currentLongTermMemoryEnabled = Get-EnvOrDefault -FilePath $envFilePath -Name 'LONG_TERM_MEMORY_ENABLED' -DefaultValue 'true'
$resolvedLongTermMemoryEnabled = Resolve-BoolEnvValue -RequestedValue $LongTermMemoryEnabled -CurrentValue $currentLongTermMemoryEnabled -DefaultValue 'true'
Upsert-EnvVar -FilePath $envFilePath -Name 'LONG_TERM_MEMORY_ENABLED' -Value $resolvedLongTermMemoryEnabled

$currentSessionDistillationEnabled = Get-EnvOrDefault -FilePath $envFilePath -Name 'SESSION_DISTILLATION_ENABLED' -DefaultValue 'true'
$resolvedSessionDistillationEnabled = Resolve-BoolEnvValue -RequestedValue $SessionDistillationEnabled -CurrentValue $currentSessionDistillationEnabled -DefaultValue 'true'
Upsert-EnvVar -FilePath $envFilePath -Name 'SESSION_DISTILLATION_ENABLED' -Value $resolvedSessionDistillationEnabled

$currentFailureJournalEnabled = Get-EnvOrDefault -FilePath $envFilePath -Name 'FAILURE_JOURNAL_ENABLED' -DefaultValue 'true'
$resolvedFailureJournalEnabled = Resolve-BoolEnvValue -RequestedValue $FailureJournalEnabled -CurrentValue $currentFailureJournalEnabled -DefaultValue 'true'
Upsert-EnvVar -FilePath $envFilePath -Name 'FAILURE_JOURNAL_ENABLED' -Value $resolvedFailureJournalEnabled

$currentLongTermMemoryDbPath = Get-EnvOrDefault -FilePath $envFilePath -Name 'LONG_TERM_MEMORY_DB_PATH' -DefaultValue 'memory_store/long_term.db'
$resolvedLongTermMemoryDbPath = if (($LongTermMemoryDbPath ?? '').Trim()) { $LongTermMemoryDbPath.Trim() } else { $currentLongTermMemoryDbPath }
Upsert-EnvVar -FilePath $envFilePath -Name 'LONG_TERM_MEMORY_DB_PATH' -Value $resolvedLongTermMemoryDbPath

Write-Host "Long-term memory flags: LTM=$resolvedLongTermMemoryEnabled, Distillation=$resolvedSessionDistillationEnabled, FailureJournal=$resolvedFailureJournalEnabled" -ForegroundColor Cyan
Write-Host "Long-term memory DB path: $resolvedLongTermMemoryDbPath" -ForegroundColor Cyan

if ($selectedRuntime -eq 'api') {
    $existingApiModel = Get-EnvOrDefault -FilePath $envFilePath -Name 'API_MODEL' -DefaultValue 'minimax-m2:cloud'
    $selectedApiModel = Resolve-ApiModel -CurrentApiModel $existingApiModel
    Upsert-EnvVar -FilePath $envFilePath -Name 'API_BASE_URL' -Value "http://localhost:$LlmPort/api"
    Upsert-EnvVar -FilePath $envFilePath -Name 'API_MODEL' -Value $selectedApiModel
}

$localModel = Get-EnvOrDefault -FilePath $envFilePath -Name 'LOCAL_MODEL' -DefaultValue 'llama3.3:70b-instruct-q4_K_M'
$apiModel = Get-EnvOrDefault -FilePath $envFilePath -Name 'API_MODEL' -DefaultValue 'minimax-m2:cloud'
$selectedModel = if ($selectedRuntime -eq 'api') { $apiModel } else { $localModel }
if ($selectedRuntime -eq 'api') {
    Ensure-CloudLogin -OllamaBin $ollamaBinary -ModelName $selectedModel
}
Ensure-SelectedModelInstalled -OllamaBin $ollamaBinary -ModelName $selectedModel -RuntimeMode $selectedRuntime
Ensure-SelectedModelRunnable -Port $LlmPort -ModelName $selectedModel -RuntimeMode $selectedRuntime

Set-RuntimeState -Mode $selectedRuntime -Port $LlmPort
Set-Location $backendDir

$venvPython = Ensure-BackendVenv312 -BackendDirPath $backendDir
Invoke-PipInstall -PythonExe $venvPython -Arguments @('install', '--upgrade', 'pip') -StepName 'upgrade-pip'
Invoke-PipInstall -PythonExe $venvPython -Arguments @('install', '-r', 'requirements.txt') -StepName 'install-requirements'

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
