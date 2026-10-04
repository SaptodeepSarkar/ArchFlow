#!/usr/bin/env bash
# One-shot, aggregate-only V5/V6 comparison on the frozen Indian-English set.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${PYTHON:-python3}
base_model= candidate_model= manifest= out= device=cpu beam_size=5

usage() {
  printf '%s\n' 'usage: qualify-v6-monsoon.sh --base-ct2 PATH --candidate-ct2 PATH --manifest PATH --out PATH [--device cpu|cuda] [--beam-size N]'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-ct2) base_model=$2; shift 2 ;;
    --candidate-ct2) candidate_model=$2; shift 2 ;;
    --manifest) manifest=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    --device) device=$2; shift 2 ;;
    --beam-size) beam_size=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

for name in base_model candidate_model manifest out; do
  [[ -n "${!name}" ]] || { usage >&2; exit 64; }
done
for path in "$base_model" "$candidate_model" "$manifest" "$(dirname "$manifest")/provenance.json"; do
  [[ -e "$path" ]] || { printf 'missing qualification input: %s\n' "$path" >&2; exit 66; }
done
[[ "$device" == cpu || "$device" == cuda ]] || { usage >&2; exit 64; }
[[ "$beam_size" =~ ^[1-9][0-9]*$ ]] || { printf 'beam size must be positive\n' >&2; exit 64; }

# The public test is intended to prove V6 against the model actually selected
# as V5 in this workspace, not an arbitrary clean Whisper checkpoint. Pin the
# current supervised-200 CT2 artifact resolved by recognition.model="v5";
# update only when the product's V5 resolver/artifact itself is replaced.
expected_v5_sha256=73f73065f95036f184910da576d0ca66ab5a1ef62f077d8dfbe8a029c59d5427
actual_base_sha256=$("$python_bin" - "$repo_root/tools" "$base_model" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from eval_v6_linux_ct2 import model_sha256
from pathlib import Path
print(model_sha256(Path(sys.argv[2])))
PY
)
[[ "$actual_base_sha256" == "$expected_v5_sha256" ]] || {
  printf 'refusing V5/V6 qualification: base model is not the pinned deployed V5 artifact (%s)\n' "$actual_base_sha256" >&2
  exit 65
}

# Pin the one authorized public-test artifact and prove the staged manifest has
# not changed. The manifest contains only audio references and transcripts;
# demographic/device columns were discarded by the staging tool.
"$python_bin" - "$manifest" "$(dirname "$manifest")/provenance.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest, provenance = map(Path, sys.argv[1:])
expected_hash = "27532276684372c79febcc1c1ba7a7bca84eda9ae6e31d93804c194522b9a0ca"
doc = json.loads(provenance.read_text(encoding="utf-8"))
actual_hash = hashlib.sha256(manifest.read_bytes()).hexdigest()
if actual_hash != expected_hash or doc.get("minimal_manifest_sha256") != expected_hash:
    raise SystemExit("refusing evaluation: frozen Monsoon manifest hash mismatch")
if (doc.get("dataset") != "VoiceArena/MonsoonASR-Open-ASR-leaderboard-en-IN"
        or doc.get("revision") != "bc1da7b42ef6e2853123c97bf6d22067e4802d11"
        or doc.get("rows") != 2102
        or doc.get("split") != "test (public; evaluation only)"):
    raise SystemExit("refusing evaluation: unexpected Monsoon provenance")
with manifest.open(encoding="utf-8") as handle:
    rows = sum(bool(line.strip()) for line in handle)
if rows != 2102:
    raise SystemExit("refusing evaluation: unexpected Monsoon row count")
PY

out_abs=$(realpath -m "$out")
case "$out_abs/" in
  "$repo_root/"*) printf 'evaluation reports must stay outside Git: %s\n' "$out_abs" >&2; exit 73 ;;
esac

# Persist a candidate/base hash claim beside the frozen local benchmark. A
# completed result is immutable: a later model cannot consume the public test
# after seeing an earlier candidate's score. A same-hash retry is permitted
# only when an earlier invocation failed before writing a completion receipt.
claim="$(dirname "$manifest")/.v6-model-eval-claim.json"
receipt="$(dirname "$manifest")/.v6-model-eval-complete.json"
model_hashes=$("$python_bin" - "$repo_root/tools" "$base_model" "$candidate_model" <<'PY'
import json
import sys
sys.path.insert(0, sys.argv[1])
from eval_v6_linux_ct2 import model_sha256
from pathlib import Path
print(json.dumps({"base_model_sha256": model_sha256(Path(sys.argv[2])),
                  "candidate_model_sha256": model_sha256(Path(sys.argv[3]))}, sort_keys=True))
PY
)
if [[ -e "$receipt" ]]; then
  "$python_bin" - "$claim" "$receipt" "$model_hashes" "$device" "$beam_size" <<'PY'
import json
import sys
from pathlib import Path
claim_path, receipt_path = map(Path, sys.argv[1:3])
claimed = json.loads(claim_path.read_text(encoding="utf-8"))
current = {**json.loads(sys.argv[3]), "device": sys.argv[4], "beam_size": int(sys.argv[5])}
if any(claimed.get(key) != value for key, value in current.items()):
    raise SystemExit("refusing a different model or decoder: the frozen public test is complete")
done = json.loads(receipt_path.read_text(encoding="utf-8"))
print("one-shot evaluation already completed; comparison report: " + done["comparison_report"])
PY
  exit 0
fi
[[ ! -e "$out_abs" ]] || { printf 'refusing to overwrite one-shot evaluation output: %s\n' "$out_abs" >&2; exit 73; }
if [[ -e "$claim" ]]; then
  "$python_bin" - "$claim" "$model_hashes" "$device" "$beam_size" <<'PY'
import json
import sys
from pathlib import Path
claimed = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
current = {**json.loads(sys.argv[2]), "device": sys.argv[3], "beam_size": int(sys.argv[4])}
if any(claimed.get(key) != value for key, value in current.items()):
    raise SystemExit("refusing a different model: the frozen public test is already claimed")
PY
else
  "$python_bin" - "$claim" "$model_hashes" "$manifest" "$device" "$beam_size" <<'PY'
import json
import sys
from pathlib import Path
path = Path(sys.argv[1])
record = {**json.loads(sys.argv[2]), "manifest_sha256": "27532276684372c79febcc1c1ba7a7bca84eda9ae6e31d93804c194522b9a0ca",
          "device": sys.argv[4], "beam_size": int(sys.argv[5])}
with path.open("x", encoding="utf-8") as handle:
    json.dump(record, handle, sort_keys=True)
    handle.write("\n")
PY
fi
mkdir -p "$out_abs"

for protocol in base candidate; do
  model=$base_model
  [[ "$protocol" != candidate ]] || model=$candidate_model
  "$python_bin" "$repo_root/tools/eval_v6_linux_ct2.py" \
    --manifest "$manifest" --audio-root "$(dirname "$manifest")" \
    --model "$model" --report "$out_abs/$protocol.json" \
    --limit 0 --device "$device" --beam-size "$beam_size"
done

# Distinct model hashes are expected here; the frozen source manifest, selected
# IDs, and decoder settings must match exactly. This benchmark is run once only
# after the candidate and decoding configuration have been frozen.
"$python_bin" "$repo_root/tools/compare_v6_whisper_evals.py" \
  --base "$out_abs/base.json" --candidate "$out_abs/candidate.json" \
  --report "$out_abs/comparison.json" --allow-model-mismatch \
  --minimum-wer-improvement 0 --maximum-protected-term-drop 0

"$python_bin" - "$out_abs" "$receipt" <<'PY'
import json
import sys
from pathlib import Path
out, receipt = map(Path, sys.argv[1:3])
base = json.loads((out / "base.json").read_text(encoding="utf-8"))
candidate = json.loads((out / "candidate.json").read_text(encoding="utf-8"))
comparison = json.loads((out / "comparison.json").read_text(encoding="utf-8"))
record = {
    "manifest_sha256": base["source_manifest_sha256"],
    "base_model_sha256": base["model_sha256"],
    "candidate_model_sha256": candidate["model_sha256"],
    "decoder": base["decoder"],
    "base_wer_percent": base["normalized_wer_percent"],
    "candidate_wer_percent": candidate["normalized_wer_percent"],
    "promotion_eligible": comparison["promotion_eligible"],
    "comparison_report": str(out / "comparison.json"),
}
with receipt.open("x", encoding="utf-8") as handle:
    json.dump(record, handle, sort_keys=True, indent=2)
    handle.write("\n")
PY

printf 'Aggregate-only one-shot reports saved at %s\n' "$out_abs"
