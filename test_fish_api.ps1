$ErrorActionPreference = "Stop"

@'
from pathlib import Path
from novel_tts.fish_provider import request_fish_tts

output = Path("output/previews/fish_api_test.mp3")
request_fish_tts(
    text="這是一段 Fish Speech API 測試。",
    output=output,
    server_url="http://127.0.0.1:8080/v1/tts",
)
print(output)
'@ | python -
