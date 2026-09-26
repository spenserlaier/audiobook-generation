#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
breeze_runtime_dir="${AUDIOBOOK_DATA_DIR:-data}/breeze-runtime"
breeze_python="${BREEZE_PYTHON:-python3.12}"

if ! command -v uv >/dev/null 2>&1; then
  echo "Install uv before setting up Breeze TTS 2." >&2
  exit 1
fi
if [ ! -f "$breeze_runtime_dir/source/breeze_infer/api.py" ]; then
  git clone --depth 1 https://github.com/breezeblue-ai/breeze-tts.git "$breeze_runtime_dir/source"
fi
if [ ! -x "$breeze_runtime_dir/.venv/bin/python" ]; then
  uv venv --python "$breeze_python" "$breeze_runtime_dir/.venv"
fi
uv pip install --python "$breeze_runtime_dir/.venv/bin/python" \
  -r "$breeze_runtime_dir/source/requirements.txt"
"$breeze_runtime_dir/.venv/bin/hf" download BreezeBlue/Breeze-TTS-2 \
  --local-dir "$breeze_runtime_dir/checkpoint"

echo "Breeze is ready. The audiobook server will start it on the first Breeze request."
