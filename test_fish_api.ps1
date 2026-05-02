$ErrorActionPreference = "Stop"

@'
from pathlib import Path
from novel_tts.fish_provider import request_fish_tts

output = Path("output/previews/fish_api_test.mp3")
request_fish_tts(
    text="\u4f60\u597d\uff0c\u9019\u662f Fish Speech API \u6e2c\u8a66\u3002",
    output=output,
    server_url="http://127.0.0.1:8081/v1/tts",
    max_new_tokens=32,
)
print(output)
'@ | python -
