param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765,
    [switch]$NoBrowser
)

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {
    $url = "http://$BindHost`:$Port"
    Write-Host "Starting Substrate AI Design Studio at $url" -ForegroundColor Cyan
    if (-not $NoBrowser) {
        Start-Job -ScriptBlock {
            param($targetUrl)
            Start-Sleep -Seconds 2
            Start-Process $targetUrl
        } -ArgumentList $url | Out-Null
    }
    python -m uvicorn AIstudio.backend.server:app --host $BindHost --port $Port
}
finally {
    Pop-Location
}
