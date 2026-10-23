#!/usr/bin/env bash
# One command for the V8 run: STT -> unload -> formatter -> exports -> evals -> report.
# `--session-limit-min 660` stops with status "resumable" before Colab kills the VM.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="full"
SESSION_LIMIT="${VAANI_SESSION_LIMIT_MIN:-660}"

usage() {
  sed -n '2,3p' "$0"
  echo "usage: $0 [--smoke|--full] [--session-limit-min MINUTES]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) MODE="smoke"; shift ;;
    --full) MODE="full"; shift ;;
    --session-limit-min) SESSION_LIMIT="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

DATA="${VAANI_DATA_DIR:-/content/vaani-data}"
[[ -d "$DATA" ]] || DATA="$(dirname "$here")/.data/v8"
OUT="${VAANI_OUT_DIR:-/content/vaani-out}"
[[ -d /content ]] || OUT="$here/out"
PY="${VAANI_PYTHON:-python3}"
STT_MODEL="${VAANI_STT_MODEL:-openai/whisper-large-v3-turbo}"
FMT_MODEL="${VAANI_FMT_MODEL:-Qwen/Qwen2.5-1.5B-Instruct}"

mkdir -p "$OUT/logs" "$OUT/eval" "$OUT/export"
if [[ "$MODE" == "smoke" ]]; then
  MAX_STEPS=20
  EXTRA=(--smoke)
  LIMIT=(--eval-limit 8)
  DRY=(--dry-run)
  EVAL_LIMIT=(--limit 8)
else
  MAX_STEPS=0
  EXTRA=()
  LIMIT=()
  DRY=()
  EVAL_LIMIT=()
fi

stage_status() {
  "$PY" - "$OUT/state.json" "$1" <<'PY'
import json, sys
try:
    state = json.load(open(sys.argv[1]))
except Exception:
    state = {}
print(state.get("stages", {}).get(sys.argv[2], {}).get("status", "pending"))
PY
}

echo "=== V8 $MODE run: data=$DATA out=$OUT session_limit=${SESSION_LIMIT}min"

if [[ "$(stage_status stt)" != "done" ]]; then
  echo "--- STT $(date -u +%FT%TZ)"
  "$PY" "$here/stt_train.py" --config "$here/configs/stt.json" --data "$DATA" --out "$OUT" \
    --model "$STT_MODEL" --max-steps "$MAX_STEPS" --session-limit-min "$SESSION_LIMIT" \
    "${EXTRA[@]}" "${LIMIT[@]}" 2>&1 | tee -a "$OUT/logs/stt.log"
  if [[ "$(stage_status stt)" != "done" ]]; then
    echo "STT stopped resumable ($(stage_status stt)); rerun the same command to continue."
    exit 0
  fi
fi
echo "--- STT done; unloading before the formatter loads"
"$PY" -c "import torch; torch.cuda.empty_cache()" || true

if [[ "$(stage_status formatter)" != "done" ]]; then
  echo "--- formatter $(date -u +%FT%TZ)"
  "$PY" "$here/formatter_train.py" --config "$here/configs/formatter.json" --data "$DATA" --out "$OUT" \
    --model "$FMT_MODEL" --max-steps "$MAX_STEPS" --session-limit-min "$SESSION_LIMIT" \
    "${EXTRA[@]}" "${LIMIT[@]}" 2>&1 | tee -a "$OUT/logs/formatter.log"
  if [[ "$(stage_status formatter)" != "done" ]]; then
    echo "formatter stopped resumable ($(stage_status formatter)); rerun the same command."
    exit 0
  fi
fi

echo "--- exports"
"$PY" "$here/export_stt_ct2.py" --model "$OUT/stt/averaged" \
  --out "$OUT/export/stt-ct2-int8" "${DRY[@]}" 2>&1 | tee -a "$OUT/logs/export.log"
bash "$here/export_formatter_gguf.sh" --model "$OUT/formatter/averaged" \
  --out "$OUT/export/formatter-q4_k_m.gguf" "${DRY[@]}" 2>&1 | tee -a "$OUT/logs/export.log"

echo "--- evals"
"$PY" "$here/eval_stt.py" --model "$OUT/stt/averaged" --data "$DATA" --split test \
  --eval-dir "$OUT/eval" "${EVAL_LIMIT[@]}" 2>&1 | tee -a "$OUT/logs/eval-stt.log"
"$PY" "$here/eval_formatter.py" --model "$OUT/formatter/averaged" --data "$DATA" --split test \
  --eval-dir "$OUT/eval" "${EVAL_LIMIT[@]}" 2>&1 | tee -a "$OUT/logs/eval-formatter.log"

"$PY" "$here/report.py" --out "$OUT"
echo "=== V8 $MODE run complete: $OUT/report.md"
