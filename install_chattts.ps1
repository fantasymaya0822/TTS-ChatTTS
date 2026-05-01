$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
python -m pip install -r requirements-chattts.txt
python -m novel_tts.cli chattts-preload
