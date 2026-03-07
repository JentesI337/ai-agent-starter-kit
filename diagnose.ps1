<#
.SYNOPSIS
    Quick diagnostic for the AI Agent Starter Kit.
.DESCRIPTION
    Checks REST endpoints, then sends a test message via WebSocket
    and validates the full pipeline lifecycle.
.PARAMETER BaseUrl
    Backend URL (default: http://localhost:8000)
.PARAMETER Prompt
    Test prompt to send (default: simple math question)
.PARAMETER Timeout
    WebSocket timeout in seconds (default: 90)
.PARAMETER Verbose
    Print every WebSocket event
#>
param(
    [string]$BaseUrl = "http://localhost:8000",
    [string]$Prompt = "",
    [int]$Timeout = 90,
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "ERROR: Backend venv not found at $venvPython" -ForegroundColor Red
    Write-Host "Run start-dev.ps1 first to set up the environment." -ForegroundColor Yellow
    exit 1
}

$scriptPath = Join-Path $PSScriptRoot "backend\scripts\diagnose.py"

$args_ = @("$scriptPath", "--base-url", $BaseUrl, "--timeout", $Timeout)
if ($Prompt) { $args_ += @("--prompt", $Prompt) }
if ($Verbose) { $args_ += "--verbose" }

& $venvPython @args_
exit $LASTEXITCODE
