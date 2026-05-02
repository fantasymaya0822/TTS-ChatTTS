$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv-fish-xpu\Scripts\python.exe"
$fishRoot = Join-Path $PSScriptRoot "external\fish-speech"
$checkpoint = "\\wsl.localhost\Ubuntu\home\mywsl\fish-speech\checkpoints\s2-pro"
$listen = "127.0.0.1:8081"
$stdout = Join-Path $PSScriptRoot "output\fish_xpu_server.out.log"
$stderr = Join-Path $PSScriptRoot "output\fish_xpu_server.err.log"

if (-not (Test-Path $python)) {
    throw "Missing .venv-fish-xpu. Run setup_fish_xpu_windows.ps1 first."
}

if (-not (Test-Path $fishRoot)) {
    throw "Missing external\fish-speech. Clone https://github.com/fishaudio/fish-speech.git into external\fish-speech first."
}

if (-not (Test-Path $checkpoint)) {
    throw "Missing checkpoint path: $checkpoint"
}

New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot "output") | Out-Null
Remove-Item -LiteralPath $stdout, $stderr -Force -ErrorAction SilentlyContinue

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$args = @(
    "-u",
    "tools\api_server.py",
    "--llama-checkpoint-path", $checkpoint,
    "--decoder-checkpoint-path", (Join-Path $checkpoint "codec.pth"),
    "--device", "xpu",
    "--max-text-length", "256",
    "--listen", $listen
)

$process = Start-Process `
    -FilePath $python `
    -ArgumentList $args `
    -WorkingDirectory $fishRoot `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Fish Speech XPU server starting on http://$listen"
Write-Host "PID: $($process.Id)"
Write-Host "Log: $stderr"
Write-Host "Health check:"
Write-Host "  Invoke-RestMethod http://127.0.0.1:8081/v1/health"
