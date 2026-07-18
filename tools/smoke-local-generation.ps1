$ErrorActionPreference = "Stop"
$Root = Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $Root "lyricmorph-backend"
$Sample = Join-Path $BackendDir "sample-voice.wav"
$Output = Join-Path $BackendDir "offline-prototype-demo.mp3"

function Find-Python {
  if ($env:SKARLY_PYTHON -and (Test-Path -LiteralPath $env:SKARLY_PYTHON)) {
    return $env:SKARLY_PYTHON
  }
  foreach ($candidate in @("python", "py", "$env:USERPROFILE\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe")) {
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

$Python = Find-Python
@"
import math, struct, wave
path = r"$Sample"
sample_rate = 44100
seconds = 8
with wave.open(path, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)
    for i in range(sample_rate * seconds):
        t = i / sample_rate
        gate = 0.5 + 0.5 * math.sin(2 * math.pi * 0.55 * t)
        envelope = min(1.0, t / 0.3) * min(1.0, (seconds - t) / 0.6)
        vibrato = 5 * math.sin(2 * math.pi * 5.2 * t)
        tone = math.sin(2 * math.pi * (205 + vibrato) * t) * 0.28
        overtone = math.sin(2 * math.pi * (410 + vibrato) * t) * 0.07
        sample = (tone + overtone) * envelope * (0.45 + 0.55 * gate)
        wav.writeframesraw(struct.pack("<h", int(max(-0.95, min(0.95, sample)) * 32767)))
"@ | & $Python -

$headers = @{ Authorization = "Bearer guest:guest-session" }
$signBody = @{
  filename = "sample-voice.wav"
  content_type = "audio/wav"
  size_bytes = (Get-Item -LiteralPath $Sample).Length
  source_type = "recording"
} | ConvertTo-Json

$signed = Invoke-RestMethod -Uri "http://127.0.0.1:8090/v1/uploads/sign" -Method Post -Headers $headers -ContentType "application/json" -Body $signBody
Invoke-RestMethod -Uri $signed.upload_url -Method Put -ContentType "audio/wav" -InFile $Sample | Out-Null

$jobBody = @{
  raw_audio_path = $signed.raw_audio_path
  genre = "Lo-fi"
  track_name = "Offline Prototype Demo"
  source_type = "recording"
  delete_raw_after_mix = $false
} | ConvertTo-Json

$job = Invoke-RestMethod -Uri "http://127.0.0.1:8090/v1/jobs" -Method Post -Headers $headers -ContentType "application/json" -Body $jobBody
for ($i = 0; $i -lt 90; $i++) {
  Start-Sleep -Seconds 1
  $result = Invoke-RestMethod -Uri "http://127.0.0.1:8090/v1/jobs/$($job.job.job_id)" -Method Get -Headers $headers
  Write-Host "poll=$i status=$($result.job.status) stage=$($result.job.stage)"
  if ($result.job.status -in @("ready", "failed")) { break }
}

if ($result.job.status -ne "ready") {
  $result | ConvertTo-Json -Depth 8
  throw "Generation did not become ready."
}

Invoke-WebRequest -Uri $result.final_mp3_download_url -OutFile $Output -UseBasicParsing
Write-Host "Generated $Output"
Write-Host "Bytes: $((Get-Item -LiteralPath $Output).Length)"
