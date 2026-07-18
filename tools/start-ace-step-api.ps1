param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8001,
    [switch]$NoInit
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$workspaceRoot = Split-Path -Parent $projectRoot
$aceRoot = if ($env:SKARLY_ACE_STEP_REPO) {
    $env:SKARLY_ACE_STEP_REPO
} else {
    Join-Path $workspaceRoot "skarly-ai-repos\ACE-Step-1.5"
}
$uvExe = Join-Path $workspaceRoot "skarly-ai-repos\_tooling\.venv\Scripts\uv.exe"

if (-not (Test-Path $aceRoot)) {
    throw "ACE-Step repo not found at $aceRoot. Pull/build AI repos first."
}

if ($NoInit) {
    $env:ACESTEP_NO_INIT = "true"
}

if (-not $env:ACESTEP_INIT_LLM) {
    $env:ACESTEP_INIT_LLM = "auto"
}

Write-Host "Starting ACE-Step API at http://$HostName`:$Port"
Write-Host "Repo: $aceRoot"

Push-Location $aceRoot
try {
    if (Test-Path $uvExe) {
        & $uvExe run --no-sync acestep-api --host $HostName --port $Port
    } elseif (Test-Path ".\start_api_server.bat") {
        & ".\start_api_server.bat"
    } else {
        throw "Could not find uv or start_api_server.bat for ACE-Step."
    }
} finally {
    Pop-Location
}
