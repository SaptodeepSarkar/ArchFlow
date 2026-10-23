#!/usr/bin/env bash
# Serve Vaani's *fine-tuned* formatter: the base GGUF plus the LoRA adapter the
# training run produced, through llama.cpp.
#
# Vaani talks OpenAI chat to VAANI_LLM_ENDPOINT, so pointing that at this port
# is the whole integration -- no code change, and the rule-engine fallback still
# covers this server being down.
#
# Overridable (defaults are this machine's layout, like install.sh's KYPY):
#   VAANI_FMT_LLAMA_SERVER  llama-server binary
#   VAANI_FMT_BASE_GGUF     base model, must be the one the adapter was built on
#   VAANI_FMT_LORA_GGUF     adapter converted by convert_lora_to_gguf.py
#   VAANI_LLM_PORT          bind port (default 8082; 8081 is the untuned server)
#   VAANI_FMT_GPU_LAYERS    layers on GPU (0 = CPU, for when VRAM is busy)
#
# Usage: serve-formatter.sh [extra llama-server args...]
set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
R="$REPO/.research/indic-stt-llm-training"

LLAMA="${VAANI_FMT_LLAMA_SERVER:-/home/saptodeep/Projects/Kyuma/model-server/vendor/llama-b11588/llama-server}"
BASE="${VAANI_FMT_BASE_GGUF:-/home/saptodeep/Projects/Kyuma/models/qwen2.5-1.5b-instruct-q4_k_m.gguf}"
LORA="${VAANI_FMT_LORA_GGUF:-$R/out/formatter-lora.gguf}"
PORT="${VAANI_LLM_PORT:-8082}"
GPU_LAYERS="${VAANI_FMT_GPU_LAYERS:-99}"

for f in "$LLAMA" "$BASE" "$LORA"; do
  [ -e "$f" ] || {
    echo "serve-formatter: missing $f" >&2
    echo "  (set VAANI_FMT_LLAMA_SERVER / VAANI_FMT_BASE_GGUF / VAANI_FMT_LORA_GGUF)" >&2
    exit 1
  }
done

echo "serve-formatter: base=$(basename "$BASE") lora=$(basename "$LORA") -> http://127.0.0.1:$PORT" >&2
echo "serve-formatter: set VAANI_LLM_ENDPOINT=http://127.0.0.1:$PORT" >&2
exec "$LLAMA" -m "$BASE" --lora "$LORA" \
  --host 127.0.0.1 --port "$PORT" -c 2048 \
  --n-gpu-layers "$GPU_LAYERS" "$@"
