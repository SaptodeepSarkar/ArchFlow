#!/usr/bin/env bash
# Serve Vaani's fine-tuned STT re-decode model (base Whisper + LoRA adapter).
#
# The daemon calls this over HTTP at the end of an utterance, after the fast
# streaming pass has already shown live words. Point the daemon at it with
# VAANI_STT_REFINE_ENDPOINT (and enable the pass with VAANI_STT_REFINE_BACKEND,
# which install.sh writes when you opt in).
#
# Overridable:
#   VAANI_REFINE_PYTHON   python that has torch+transformers+peft (the training
#                         venv is the default; there is no CT2 dependency)
#   VAANI_STT_ADAPTER     LoRA dir to serve; default is the best checkpoint
#                         (step 50), not the final one -- see the build log
#
# Usage: serve-refine-stt.sh [extra serve-refine-stt.py args...]
set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
R="$REPO/.research/indic-stt-llm-training"

PY="${VAANI_REFINE_PYTHON:-$R/venv/bin/python}"
ADAPTER="${VAANI_STT_ADAPTER:-$R/out/stt-checkpoints/step-50}"

[ -x "$PY" ] || {
  echo "serve-refine-stt: no python at $PY (set VAANI_REFINE_PYTHON)" >&2
  exit 1
}
[ -f "$ADAPTER/adapter_config.json" ] || {
  echo "serve-refine-stt: no LoRA adapter at $ADAPTER (set VAANI_STT_ADAPTER)" >&2
  exit 1
}

exec "$PY" "$REPO/packaging/serve-refine-stt.py" --adapter "$ADAPTER" "$@"
