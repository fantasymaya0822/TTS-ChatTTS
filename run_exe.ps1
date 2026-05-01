$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
Start-Process -FilePath ".\dist\NovelEdgeTTS\NovelEdgeTTS.exe"
