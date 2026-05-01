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

## 注意

Fish Speech API 回傳的每小段 MP3 會先放在：

```text
<project>/temp/fish/<chapter>/
```

每章完成後會合併到：

```text
<project>/chapters/
```
