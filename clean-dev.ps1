param(
    [int]$LlmPort = 11434,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 4200,
    [switch]$IncludeLlm
)

$ErrorActionPreference = 'Stop'

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
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

function Stop-PortProcess([int]$Port, [string]$ServiceName) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $connections) {
        Write-Host "No listener on port $Port for $ServiceName"
        return
    }

    $pids = $connections | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 0 -and $_ -ne $PID }
    if (-not $pids) {
        Write-Host "No killable process found on port $Port for $ServiceName"
        return
    }

    foreach ($procId in $pids) {
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            $name = if ($proc) { $proc.ProcessName } else { 'unknown' }
            Write-Host "Stopping $ServiceName listener on port $Port (PID=$procId, Name=$name)"
            Stop-Process -Id $procId -Force -ErrorAction Stop
        }
        catch {
            Write-Host "Warning: Could not stop PID $procId on port $Port. $_" -ForegroundColor Yellow
        }
    }

    for ($i = 0; $i -lt 12; $i++) {
        if (-not (Test-TcpPort -HostName '127.0.0.1' -Port $Port)) {
            Write-Host "$ServiceName port $Port is now free"
            return
        }
        Start-Sleep -Milliseconds 250
    }

    Write-Host "Warning: Port $Port may still be in use for $ServiceName" -ForegroundColor Yellow
}

Write-Step "Cleaning development ports"
Stop-PortProcess -Port $BackendPort -ServiceName 'backend'
Stop-PortProcess -Port $FrontendPort -ServiceName 'frontend'

if ($IncludeLlm) {
    Stop-PortProcess -Port $LlmPort -ServiceName 'llm'
}

Write-Host "Cleanup complete"
