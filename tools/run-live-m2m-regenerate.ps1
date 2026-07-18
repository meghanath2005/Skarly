param(
    [Parameter(Mandatory = $true)]
    [string]$JobId,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,
    [string]$EditInstruction = "Regenerate as a sparse electronic ambient arrangement with new synth harmony, restrained percussion, and no rock guitars.",
    [string]$BaseUrl = "http://127.0.0.1:8090"
)

$ErrorActionPreference = "Stop"
$started = Get-Date
$payload = @{
    edit_instruction = $EditInstruction
    candidate_count = 1
    provider_preference = "ace_step"
    rights_confirmed = $true
} | ConvertTo-Json -Depth 6

try {
    $response = Invoke-RestMethod -Uri "$BaseUrl/v2/jobs/$JobId/regenerate" -Method Post -ContentType "application/json" -Body $payload -TimeoutSec 3600
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
