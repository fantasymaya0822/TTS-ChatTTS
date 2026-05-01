$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
python -m pip install -r requirements-chattts.txt
python -m pip install -r requirements-dev.txt
python -m pip install -r requirements-fish.txt
python -m PyInstaller .\novel_chattts_tts.spec --clean --noconfirm
Write-Host ""
Write-Host "Built: $PSScriptRoot\dist\NovelChatTTS\NovelChatTTS.exe"
