$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv-fish-xpu\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Missing .venv-fish-xpu. Create it with:"
    Write-Host "  py -3.12 -m venv .venv-fish-xpu"
    Write-Host "  .\.venv-fish-xpu\Scripts\python.exe -m pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/xpu"
    exit 1
}

@'
import time
import torch

print("torch", torch.__version__)
print("has xpu", hasattr(torch, "xpu"))
available = hasattr(torch, "xpu") and torch.xpu.is_available()
print("xpu available", available)

if not available:
    raise SystemExit(2)

print("xpu count", torch.xpu.device_count())
for index in range(torch.xpu.device_count()):
    print("device", index, torch.xpu.get_device_name(index))

start = time.time()
a = torch.randn((2048, 2048), device="xpu")
b = torch.randn((2048, 2048), device="xpu")
c = a @ b
torch.xpu.synchronize()
print("matmul ok", tuple(c.shape), "seconds", round(time.time() - start, 3), "device", c.device)
'@ | & $python -
