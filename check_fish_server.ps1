$ErrorActionPreference = "Stop"

$url = "http://127.0.0.1:8080/v1/health"

try {
    $response = Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 10
    Write-Host "Fish Speech server health:"
    $response | ConvertTo-Json -Depth 5
} catch {
    Write-Host "Fish Speech server is not reachable at $url"
    Write-Host "Start it in WSL with:"
    Write-Host "  bash scripts/run_fish_speech_server_wsl.sh"
    throw
}
