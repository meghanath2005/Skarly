param(
    [Parameter(Mandatory = $true)]
    [string]$UploadId,
    [Parameter(Mandatory = $true)]
    [double]$ReferenceStrength,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [string]$StyleInstruction = "Transform this reference into a fresh cinematic rock instrumental with new harmony, drums, bass, and guitar; preserve only broad timing and energy.",
    [int]$DurationSeconds = 30,
    [string]$BaseUrl = "http://127.0.0.1:8090"
)

$ErrorActionPreference = "Stop"
$started = Get-Date
$payload = @{
    reference_upload_id = $UploadId
    rights_confirmed = $true
    provider_preference = "ace_step"
    candidate_count = 1
    duration_seconds = $DurationSeconds
    output_format = "wav"
    reference_strength = $ReferenceStrength
    genre = "Rock"
    production_style = "Cinematic Rock"
    arrangement_style = "Live band with cinematic build"
    mood_tags = @("cinematic", "driving", "original")
    instruments = @("electric guitar", "bass", "drums", "piano", "strings")
    style_instruction = $StyleInstruction
} | ConvertTo-Json -Depth 8

try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/v2/music-to-music" -Method Post -ContentType "application/json" -Body $payload -TimeoutSec 3600
    $envelope = @{
        ok = $true
        started_at = $started.ToUniversalTime().ToString("o")
        finished_at = (Get-Date).ToUniversalTime().ToString("o")
        elapsed_seconds = [Math]::Round(((Get-Date) - $started).TotalSeconds, 3)
        response = $response
    }
} catch {
    $envelope = @{
        ok = $false
        started_at = $started.ToUniversalTime().ToString("o")
        finished_at = (Get-Date).ToUniversalTime().ToString("o")
        elapsed_seconds = [Math]::Round(((Get-Date) - $started).TotalSeconds, 3)
        error = $_.Exception.Message
    }
}

$envelope | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $OutputPath -Encoding utf8
