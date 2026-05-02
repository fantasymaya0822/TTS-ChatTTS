#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/fish-speech"
cd "${ROOT}"
source .venv/bin/activate

python tools/api_server.py \
  --llama-checkpoint-path checkpoints/s2-pro \
  --decoder-checkpoint-path checkpoints/s2-pro/codec.pth \
  --device cpu \
  --listen 0.0.0.0:8080
