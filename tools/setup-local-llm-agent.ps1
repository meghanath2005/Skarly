param(
  [string]$Model = "llama3.2:1b"
)

$ErrorActionPreference = "Stop"

function Find-Ollama {
  $command = Get-Command ollama -ErrorAction SilentlyContinue
  if ($command) { return $command.Source }

  $candidates = @(
    "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ollama.Ollama_Microsoft.Winget.Source_8wekyb3d8bbwe\ollama.exe"
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  return $null
}

$Ollama = Find-Ollama
if (-not $Ollama) {
  $Winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $Winget) {
    throw "Ollama is not installed and winget is unavailable. Install Ollama from https://ollama.com/download/windows."
  }
  winget install --id Ollama.Ollama --accept-package-agreements --accept-source-agreements --scope user
  $Ollama = Find-Ollama
}

if (-not $Ollama) {
  throw "Ollama install completed, but ollama.exe was not found. Restart the terminal and try again."
}

Write-Host "Using Ollama: $Ollama"

$server = Start-Process -FilePath $Ollama -ArgumentList @("serve") -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 5

try {
  & $Ollama pull $Model
  Write-Host "Pulled model: $Model"
  Write-Host "Set SKARLY_LOCAL_LLM_MODEL=$Model in lyricmorph-backend\\.env if you changed the default."
} finally {
  if ($server -and -not $server.HasExited) {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
  }
}
