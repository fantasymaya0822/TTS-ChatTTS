# Fish Speech XPU Notes

This branch verifies the Intel Arc XPU path on Windows.

## Result

Windows native PyTorch XPU works on this machine:

```text
torch 2.13.0.dev20260501+xpu
xpu available True
device 0 Intel(R) Arc(TM) B390 GPU
```

Fish Speech API server can start with `--device xpu` after patching the external Fish Speech clone so it does not force CPU when CUDA is unavailable.

Measured short-text generation:

```text
CPU test: about 0.17 tokens/sec, about 200 sec for a tiny phrase
XPU test: about 1.38 tokens/sec, about 40 sec for the same max_new_tokens=32 request
```

So XPU is real and faster, but still not fast enough to be the main path for 5-10 MB novels.

## Setup

```powershell
powershell -ExecutionPolicy Bypass -File .\setup_fish_xpu_windows.ps1
powershell -ExecutionPolicy Bypass -File .\check_xpu_windows.ps1
```

Clone Fish Speech into the ignored external directory:

```powershell
git clone https://github.com/fishaudio/fish-speech.git .\external\fish-speech
```

Or run the helper that clones, installs without replacing XPU PyTorch, and applies the local XPU patch:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_fish_xpu_windows.ps1
```

## Required External Patch

`external\fish-speech\tools\server\model_manager.py` needs two local test changes:

1. Respect `--device xpu` when `torch.xpu.is_available()` is true.
2. Reduce warmup `max_new_tokens` from `1024` to `8`.

The external clone is ignored by git, so these changes are not committed in this repo.

## Run Server

```powershell
powershell -ExecutionPolicy Bypass -File .\run_fish_xpu_server_windows.ps1
```

The script starts:

```text
http://127.0.0.1:8081/v1/tts
```

It reuses the model downloaded in WSL:

```text
\\wsl.localhost\Ubuntu\home\mywsl\fish-speech\checkpoints\s2-pro
```

## Current Recommendation

Keep Edge TTS as the long-novel main path. Fish Speech XPU is worth keeping as an experimental local-quality option, but it still needs more work before being practical for full novels:

- GUI now avoids `max_new_tokens=0` and exposes a Fish `Max new tokens` field
- the Fish tab has a `Use local XPU server` button for `http://127.0.0.1:8081/v1/tts`
- avoid PowerShell stdin encoding for Chinese tests
- consider copying checkpoints to a local Windows path instead of reading through WSL UNC
