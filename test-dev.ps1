param(
    [switch]$SkipInstall
)

$scriptPath = Join-Path $PSScriptRoot 'start-test.ps1'
if (-not (Test-Path $scriptPath)) {
    throw "start-test.ps1 not found at $scriptPath"
}

& $scriptPath @PSBoundParameters
