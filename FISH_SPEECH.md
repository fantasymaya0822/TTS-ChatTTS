# Fish Speech 試用筆記

目前這個分支採用 **Fish Speech API 模式**，不是把 Fish Speech 模型直接包進 Windows exe。

原因：

- 官方文件建議 Linux / WSL。
- Fish Audio S2 推論建議至少 24GB VRAM。
- 直接把模型塞進 GUI exe 會很大，也比較容易和 Windows/PyInstaller 衝突。

## 官方參考

- Repo: https://github.com/fishaudio/fish-speech
- Install: https://speech.fish.audio/install/
- Server: https://speech.fish.audio/server/

## 啟動 Fish Speech Server

本專案提供兩個 WSL 輔助腳本：

```bash
bash scripts/setup_fish_speech_wsl.sh
bash scripts/run_fish_speech_server_wsl.sh
```

目前偵測到的環境：

- WSL2 / Ubuntu 可用
- Docker 未安裝
- Windows 端未偵測到 `nvidia-smi`

所以預設腳本走 CPU 安裝。CPU 可用來做功能驗證，但長篇小說會很慢；實用上仍建議 CUDA GPU。

官方文件的本機 server 範例：

```bash
python tools/api_server.py \
  --llama-checkpoint-path checkpoints/s2-pro \
  --decoder-checkpoint-path checkpoints/s2-pro/codec.pth \
  --listen 0.0.0.0:8080
```

模型權重下載：

```bash
hf download fishaudio/s2-pro --local-dir checkpoints/s2-pro
```

## GUI 設定

1. 在「全域設定」把語音引擎選成 `Fish Speech API`
2. 到 `Fish Speech` 分頁確認：
   - `Server URL`: `http://127.0.0.1:8080/v1/tts`
   - `Reference ID`: 可空白；若 server 有保存聲音參考，可填 reference id
   - `Seed`: 0 代表隨機
   - `本機切段字數`: 建議 300-800
   - `API chunk_length`: 建議 300
3. 按 `2. 開始轉檔`

## 健康檢查

Windows 端可用：

```powershell
powershell -ExecutionPolicy Bypass -File .\check_fish_server.ps1
```

API 產音測試：

```powershell
powershell -ExecutionPolicy Bypass -File .\test_fish_api.ps1
```

## 注意

Fish Speech API 回傳的每小段 MP3 會先放在：

```text
<project>/temp/fish/<chapter>/
```

每章完成後會合併到：

```text
<project>/chapters/
```
