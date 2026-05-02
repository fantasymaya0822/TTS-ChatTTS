$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv-fish-xpu\Scripts\python.exe"

if (-not (Test-Path $python)) {
    py -3.12 -m venv (Join-Path $PSScriptRoot ".venv-fish-xpu")
}

& $python -m pip install --upgrade pip setuptools wheel
& $python -m pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/xpu

Write-Host "XPU test environment is ready."
Write-Host "Run:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\check_xpu_windows.ps1"
