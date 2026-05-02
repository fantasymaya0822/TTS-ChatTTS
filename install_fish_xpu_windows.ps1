$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv-fish-xpu\Scripts\python.exe"
$fishRoot = Join-Path $PSScriptRoot "external\fish-speech"
$requirementsNoTorch = Join-Path $fishRoot "requirements-no-torch.txt"
$modelManager = Join-Path $fishRoot "tools\server\model_manager.py"

if (-not (Test-Path $python)) {
    powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "setup_fish_xpu_windows.ps1")
}

if (-not (Test-Path (Join-Path $fishRoot ".git"))) {
    New-Item -ItemType Directory -Force (Join-Path $PSScriptRoot "external") | Out-Null
    git clone https://github.com/fishaudio/fish-speech.git $fishRoot
}

@'
import tomllib
from pathlib import Path

root = Path("external/fish-speech")
data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
filtered = []
for dep in data["project"]["dependencies"]:
    name = dep.lower()
    if name.startswith("torch") or name.startswith("torchaudio"):
        continue
    filtered.append(dep)
(root / "requirements-no-torch.txt").write_text("\n".join(filtered) + "\n", encoding="utf-8")
print(root / "requirements-no-torch.txt")
'@ | & $python -

& $python -m pip install -r $requirementsNoTorch
& $python -m pip install -e $fishRoot --no-deps

$text = Get-Content -LiteralPath $modelManager -Raw
$oldDeviceBlock = @'
        # Check if MPS or CUDA is available
        if torch.backends.mps.is_available():
            self.device = "mps"
            logger.info("mps is available, running on mps.")
        elif not torch.cuda.is_available():
'@
$newDeviceBlock = @'
        # Check if XPU, MPS or CUDA is available
        if device == "xpu" and hasattr(torch, "xpu") and torch.xpu.is_available():
            self.device = "xpu"
            logger.info("xpu is available, running on xpu.")
        elif torch.backends.mps.is_available():
            self.device = "mps"
            logger.info("mps is available, running on mps.")
        elif not torch.cuda.is_available():
'@
if ($text.Contains($oldDeviceBlock)) {
    $text = $text.Replace($oldDeviceBlock, $newDeviceBlock)
}
$text = $text.Replace("max_new_tokens=1024,", "max_new_tokens=8,")
Set-Content -LiteralPath $modelManager -Value $text -Encoding UTF8

Write-Host "Fish Speech XPU install is ready."
Write-Host "Run:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\run_fish_xpu_server_windows.ps1"
