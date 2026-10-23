#!/usr/bin/env bash
# Hermetic CPU smoke: tiny random models + training/fixtures only. No 809M/1.5B
# download, no network after the venv exists. Exits 0 only if everything ran.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$here/.venv"
PY="$VENV/bin/python"
OUT="$here/out/smoke"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_PROGRESS_BARS=1

if [[ ! -x "$PY" ]]; then
  echo "=== creating $VENV (CPU torch, one time)"
  uv venv --python 3.11 "$VENV"
  uv pip install --python "$PY" --index-url https://download.pytorch.org/whl/cpu torch
  uv pip install --python "$PY" "transformers>=4.46,<5" jiwer
fi

rm -rf "$OUT"
mkdir -p "$OUT/logs" "$OUT/eval" "$OUT/export"
run() {
  local name="$1"
  shift
  echo "--- $name"
  "$@" 2>&1 | tee -a "$OUT/logs/$name.log"
}

run py_compile bash -c 'for file in "$1"/*.py; do "$2" -m py_compile "$file" || exit 1; done' _ "$here" "$PY"
for script in "$here"/*.sh; do bash -n "$script"; done

run fixtures "$PY" "$here/make_fixtures.py" --out "$here/fixtures"
run tiny-models "$PY" "$here/make_tiny_models.py" --out "$OUT/tiny"

STT=(--config "$here/configs/stt.json" --data "$here/fixtures" --out "$OUT" --model "$OUT/tiny/stt"
     --batch-size 2 --grad-accum 2 --eval-every 1 --save-every 1 --eval-limit 2)

# 1) a forced session limit must save step 0 and exit 0 with status resumable
run stt-session-limit "$PY" "$here/stt_train.py" "${STT[@]}" --max-steps 2 --session-limit-min 0.02
grep -q "SESSION LIMIT: saved step 0, resumable" "$OUT/logs/stt-session-limit.log"

# 2) resume must pick that checkpoint up and finish
run stt-train "$PY" "$here/stt_train.py" "${STT[@]}" --max-steps 2 --session-limit-min 60
grep -q "resumed from step 0" "$OUT/logs/stt-train.log"
grep -q "DONE stt" "$OUT/logs/stt-train.log"

FMT=(--config "$here/configs/formatter.json" --data "$here/fixtures" --out "$OUT" --model "$OUT/tiny/formatter"
     --batch-size 2 --grad-accum 2 --eval-every 1 --save-every 1 --eval-limit 2)

run fmt-session-limit "$PY" "$here/formatter_train.py" "${FMT[@]}" --max-steps 2 --session-limit-min 0.02
grep -q "SESSION LIMIT: saved step 0, resumable" "$OUT/logs/fmt-session-limit.log"

run fmt-train "$PY" "$here/formatter_train.py" "${FMT[@]}" --max-steps 2 --session-limit-min 60
grep -q "resumed from step 0" "$OUT/logs/fmt-train.log"
grep -q "DONE formatter" "$OUT/logs/fmt-train.log"

# 3) the opt-in packing path must also run end to end
run fmt-pack "$PY" "$here/formatter_train.py" --config "$here/configs/formatter.json" \
  --data "$here/fixtures" --out "$OUT/pack" --model "$OUT/tiny/formatter" \
  --batch-size 1 --grad-accum 1 --max-steps 1 --eval-every 1 --save-every 1 --eval-limit 1 --pack
grep -q "DONE formatter" "$OUT/logs/fmt-pack.log"

run eval-stt "$PY" "$here/eval_stt.py" --model "$OUT/stt/averaged" --data "$here/fixtures" \
  --split dev --eval-dir "$OUT/eval" --limit 2 --device cpu
run eval-formatter "$PY" "$here/eval_formatter.py" --model "$OUT/formatter/averaged" \
  --data "$here/fixtures" --split dev --eval-dir "$OUT/eval" --limit 2 --device cpu

run export-dry-runs bash -c "
  '$PY' '$here/export_stt_ct2.py' --model '$OUT/stt/averaged' --out '$OUT/export/stt-ct2-int8' --dry-run &&
  bash '$here/export_formatter_gguf.sh' --model '$OUT/formatter/averaged' \
    --out '$OUT/export/formatter-q4_k_m.gguf' --dry-run"

run report "$PY" "$here/report.py" --out "$OUT"

echo "--- assertions"
"$PY" - "$OUT" <<'PY'
import json, os, sys

out = sys.argv[1]
state = json.load(open(os.path.join(out, "state.json")))
assert state["status"] == "done", state
assert state["stages"]["stt"]["status"] == "done", state
assert state["stages"]["formatter"]["status"] == "done", state
assert isinstance(state["stages"]["stt"]["best"], (int, float)), state
assert isinstance(state["stages"]["formatter"]["best"], (int, float)), state

for stage in ("stt", "formatter"):
    ckpts = [name for name in os.listdir(os.path.join(out, stage)) if name.startswith("step-")]
    assert ckpts, f"no {stage} checkpoints"
    for name in ckpts:
        for part in ("model.pt", "optimizer.pt", "meta.json"):
            assert os.path.exists(os.path.join(out, stage, name, part)), f"{stage}/{name}/{part}"
    averaged = os.path.join(out, stage, "averaged")
    assert os.path.exists(os.path.join(averaged, "config.json")), averaged
    assert os.path.exists(os.path.join(averaged, "average.json")), averaged
    assert json.load(open(os.path.join(averaged, "average.json")))["source_steps"], averaged

stt = json.load(open(os.path.join(out, "eval", "stt.json")))
assert isinstance(stt["wer"], float) and stt["n"] == 2, stt
assert stt["per_source"], stt

formatter = json.load(open(os.path.join(out, "eval", "formatter.json")))
for key in ("exact_match", "entity_survival", "number_survival", "token_f0_5",
            "over_edit_rate", "punctuation_accuracy", "intensity_survival"):
    assert key in formatter, (key, formatter)
predictions = [line for line in open(os.path.join(out, "eval", "predictions.jsonl")) if line.strip()]
assert len(predictions) == 2, len(predictions)

for path in ("export/stt-ct2-int8/export.dry-run.json",
             "export/formatter-q4_k_m.gguf.dry-run.json",
             "report.md"):
    assert os.path.exists(os.path.join(out, path)), path
assert "V8 training report" in open(os.path.join(out, "report.md")).read()
print("smoke assertions: OK")
PY

echo "=== smoke test passed ($OUT)"
