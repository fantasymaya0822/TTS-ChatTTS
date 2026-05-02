#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/fish-speech"

sudo apt update
sudo apt install -y git git-lfs ffmpeg portaudio19-dev libsox-dev python3.12 python3.12-venv python3-pip

if [ ! -d "${ROOT}/.git" ]; then
  git clone https://github.com/fishaudio/fish-speech.git "${ROOT}"
fi

cd "${ROOT}"
git lfs install

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .[cpu]
python -m pip install "huggingface_hub[cli]"

mkdir -p checkpoints/s2-pro
HF_HUB_DISABLE_XET=1 huggingface-cli download fishaudio/s2-pro --local-dir checkpoints/s2-pro

cat <<'MSG'

Fish Speech CPU environment is ready.

Start the API server with:
  bash scripts/run_fish_speech_server_wsl.sh

Note: CPU inference can be very slow. A CUDA GPU with large VRAM is strongly recommended for real use.
MSG
