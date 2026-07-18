param(
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $Root "lyricmorph-backend"
$EnvPath = Join-Path $BackendDir ".env"
$ExampleEnvPath = Join-Path $BackendDir ".env.offline.example"

function Find-Python {
  if ($env:SKARLY_PYTHON -and (Test-Path -LiteralPath $env:SKARLY_PYTHON)) {
    return $env:SKARLY_PYTHON
  }

  $candidates = @(
    "python",
    "py",
    "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  )

  foreach ($candidate in $candidates) {
    $command = Get-Command $candidate -ErrorAction SilentlyContinue
    if (-not $command) { continue }
    try {
      $version = & $command.Source --version 2>&1
      if ($LASTEXITCODE -eq 0 -and "$version" -match "Python") {
        return $command.Source
      }
    } catch {
      continue
    }
  }

  throw "Python was not found. Install Python 3.12 or set SKARLY_PYTHON to python.exe."
}

if (-not (Test-Path -LiteralPath $EnvPath)) {
  Copy-Item -LiteralPath $ExampleEnvPath -Destination $EnvPath
}

$Python = Find-Python
$Pydeps = Join-Path $BackendDir ".pydeps"
if (-not (Test-Path -LiteralPath (Join-Path $Pydeps "fastapi"))) {
  Push-Location $BackendDir
  & $Python -m pip install -r requirements.txt --target .pydeps --upgrade
  Pop-Location
}

if (-not $NoBrowser) {
  Start-Process "http://127.0.0.1:8090/studio"
}

Push-Location $BackendDir
& $Python dev_server.py
Pop-Location
