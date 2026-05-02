# Fish Speech 使用說明

目前程式是用 **Fish Speech API 模式** 串接本機 Fish Speech server。GUI 不會把 Fish Speech 模型包進 Windows exe，因為模型和 Linux/PyTorch/CUDA 依賴太大，打包後也不適合一般 Windows 單機執行。

## 目前實測狀態

這台環境目前沒有可用的 CUDA GPU：

- WSL 裡 `torch.cuda.is_available()` 是 `False`
- Fish Speech server 會進入 CPU 模式
- `s2-pro` 模型下載成功，但 CPU 載入 server 超過 5 分鐘後仍未開啟 8080 port，程序會結束

結論：Fish Speech 可以保留在程式中當「有 GPU/遠端 API server 時使用」的選項，但不建議在目前這台 CPU-only WSL 上拿來轉 5-10MB 小說。實務上還是先用 Edge TTS 轉長篇最穩。

## 安裝與啟動

在 WSL 裡執行：

```bash
bash scripts/setup_fish_speech_wsl.sh
bash scripts/run_fish_speech_server_wsl.sh
```

安裝腳本會使用：

```bash
HF_HUB_DISABLE_XET=1 huggingface-cli download fishaudio/s2-pro --local-dir checkpoints/s2-pro
```

這是為了避免 Hugging Face Xet 下載大型 safetensors 時長時間卡住。

啟動 server：

```bash
python tools/api_server.py \
  --llama-checkpoint-path checkpoints/s2-pro \
  --decoder-checkpoint-path checkpoints/s2-pro/codec.pth \
  --device cpu \
  --listen 0.0.0.0:8080
```

如果有可用 CUDA GPU，可以把 `--device cpu` 改成 `--device cuda`。

## GUI 設定

1. 在「全域設定」選 `Fish Speech API`
2. 到「Fish Speech」頁籤設定：
   - `Server URL`: `http://127.0.0.1:8080/v1/tts`
   - `Reference ID`: Fish Speech server 裡已建立的參考音色 ID
   - `Seed`: 固定生成隨機性
   - `本機切段字數`: 建議 300-800
   - `API chunk_length`: 建議 300
   - `Max new tokens`: 建議先用 32 測試；數值越大越慢、音訊可能越長
3. 按 `2. 開始轉檔`

## 檢查 server

Windows PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\check_fish_server.ps1
```

測試 API：

```powershell
powershell -ExecutionPolicy Bypass -File .\test_fish_api.ps1
```

## 輸出位置

Fish Speech API 會先輸出分段 MP3：

```text
<project>/temp/fish/<chapter>/
```

章節合併後會放在：

```text
<project>/chapters/
```
