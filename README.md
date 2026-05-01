# Novel Edge TTS Converter

Windows desktop/CLI tool for converting large `.txt` novels into chapter-based MP3 audiobooks with Microsoft Edge online TTS voices.

Current milestone implements the local preparation pipeline plus a first GUI:

- Load large `.txt` files with encoding detection.
- Estimate character usage.
- Detect chapters.
- Split chapters into synthesis-safe text segments.
- Create a resumable project folder with `project.json`.
- Generate Edge TTS MP3 files by chapter.
- List Microsoft Edge online voices.

Azure Batch Synthesis code is still available as a fallback, but Edge TTS is now the primary path and does not require an API key.

Optional local model support:

- ChatTTS can be installed as a local provider.
- ChatTTS code is AGPL-3.0 and its released model is CC BY-NC 4.0, so treat it as non-commercial / research use.
- It is much heavier than Edge TTS and may be slow on CPU.

## Quick Start

```powershell
python -m pip install -r requirements.txt
python -m novel_tts.cli prepare "path\to\novel.txt" --out "output"
```

Run the GUI:

```powershell
.\run_gui.ps1
```

Or:

```powershell
python -m novel_tts.gui
```

GUI workflow:

1. Choose a `.txt` novel.
2. Click `讀取語音` and pick a voice.
3. Click `準備專案`.
4. Use the chapter table to inspect status or select one chapter.
5. Click `開始轉檔`.
6. Optionally click `合併整本`.

Build Windows exe:

```powershell
.\build_exe.ps1
```

If PowerShell blocks scripts on your machine, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

Output:

```text
dist\NovelEdgeTTS\NovelEdgeTTS.exe
```

Run the packaged app:

```powershell
.\run_exe.ps1
```

Optional settings:

```powershell
python -m novel_tts.cli prepare "novel.txt" --out "output" --voice "zh-TW-HsiaoChenNeural" --locale "zh-TW" --rate "+10%"
```

List Edge voices:

```powershell
python -m novel_tts.cli edge-voices --locale zh-TW
```

Convert one prepared chapter:

```powershell
python -m novel_tts.cli edge-synthesize "output\novel-name" --chapter 1 --voice zh-TW-HsiaoChenNeural --rate +10%
```

Convert all chapters:

```powershell
python -m novel_tts.cli edge-synthesize "output\novel-name" --voice zh-TW-HsiaoChenNeural --rate +10%
```

Merge chapter MP3 files into one full-book MP3:

```powershell
python -m novel_tts.cli merge-full "output\novel-name"
```

Install optional ChatTTS local model support:

```powershell
python -m pip install -r requirements-chattts.txt
```

Install and preload the local ChatTTS model:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_chattts.ps1
```

Convert one prepared chapter with ChatTTS:

```powershell
python -m novel_tts.cli chattts-synthesize "output\novel-name" --chapter 1 --speaker-seed 42
```

Use the same `--speaker-seed` to keep a consistent ChatTTS voice across chapters. In the GUI, set `ChatTTS 聲音種子`; value `0` means random.

Preview a ChatTTS seed before converting:

```powershell
python -m novel_tts.cli chattts-preview --speaker-seed 42 --text "這是一段試聽文字。"
```

In the GUI, set `ChatTTS 聲音種子`, edit `試聽文字`, then click `試聽聲音`.

Build a heavier exe that bundles ChatTTS/PyTorch runtime:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe_chattts.ps1
```

Output:

```text
dist\NovelChatTTS\NovelChatTTS.exe
```

The ChatTTS model weights are still downloaded/cached separately by Hugging Face on first use.

Check local environment:

```powershell
python -m novel_tts.cli doctor
```

FFmpeg is required when a chapter is split into multiple audio segments and needs local merging. The app first uses system FFmpeg if available, then falls back to the bundled `imageio-ffmpeg` package from `requirements.txt`.

## Output Layout

```text
output/
  novel-name/
    project.json
    chapters/
    full/
    temp/
      ssml/
      segments/
      downloads/
```
