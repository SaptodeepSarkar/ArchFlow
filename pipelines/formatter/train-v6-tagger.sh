#!/usr/bin/env bash
# Automated, leak-excluded V6 tagger candidate run. All reports are aggregate-only.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${PYTHON:-python3}

usage() {
  printf '%s\n' 'usage: pipelines/formatter/train-v6-tagger.sh --train PATH --dev PATH --test PATH --hard-eval PATH --challenge PATH --out PATH [--real-derived PATH --real-split-dir PATH] [--model hashed|bigru|conv] [--epochs N] [--min-available-mb N]'
}

train= dev= test= hard_eval= challenge= out= real_derived= real_split_dir= model=bigru epochs=20 min_available_mb=4096
while [[ $# -gt 0 ]]; do
  case "$1" in
    --train) train=$2; shift 2 ;;
    --dev) dev=$2; shift 2 ;;
    --test) test=$2; shift 2 ;;
    --hard-eval) hard_eval=$2; shift 2 ;;
    --challenge) challenge=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    --real-derived) real_derived=$2; shift 2 ;;
    --real-split-dir) real_split_dir=$2; shift 2 ;;
    --model) model=$2; shift 2 ;;
    --epochs) epochs=$2; shift 2 ;;
    --min-available-mb) min_available_mb=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

for name in train dev test hard_eval challenge out; do
  if [[ -z "${!name}" ]]; then usage >&2; exit 64; fi
done
for path in "$train" "$dev" "$test" "$hard_eval" "$challenge"; do
  [[ -f "$path" ]] || { printf 'missing input file: %s\n' "$path" >&2; exit 66; }
done
[[ "$model" == hashed || "$model" == bigru || "$model" == conv ]] || { usage >&2; exit 64; }
if [[ -n "$real_derived" || -n "$real_split_dir" ]]; then
  [[ -n "$real_derived" && -n "$real_split_dir" && -f "$real_derived" ]] || { usage >&2; exit 64; }
fi
out_abs=$(realpath -m "$out")
case "$out_abs/" in
  "$repo_root/"*) printf 'model outputs must stay outside the Git worktree: %s\n' "$out_abs" >&2; exit 73 ;;
esac
[[ ! -e "$out" ]] || {
  printf 'refusing to overwrite an existing model candidate: %s\n' "$out" >&2
  exit 73
}

(
  cd "$repo_root"
  "$python_bin" -m unittest tests/test_v6_hard_examples.py
)

mkdir -p "$out"
replay="$out/hard-replay.jsonl"
render_report="$out/replay-render.json"
challenge_report="$out/challenge-eval.json"
hard_report="$out/hard-eval.json"
train_files=("$train" "$replay")
dev_files=("$dev")
test_files=("$test")

"$python_bin" "$repo_root/tools/build_v6_hard_examples.py" \
  --count 2000 --out "$replay" \
  --exclude "$train" --exclude "$dev" --exclude "$test" \
  --exclude "$hard_eval" --exclude "$challenge"
"$python_bin" "$repo_root/tools/render_v6_edit_plan.py" --input "$replay" --report "$render_report"
"$python_bin" -c 'import json,sys; r=json.load(open(sys.argv[1])); sys.exit(0 if r["rows"] and r["exact"] == r["rows"] else 1)' "$render_report" || {
  printf '%s\n' 'replay failed deterministic render/target agreement; refusing to train' >&2
  exit 65
}

if [[ -n "$real_derived" ]]; then
  "$python_bin" "$repo_root/tools/auto_label_v6_real_derived.py" \
    --input "$real_derived" --split-dir "$real_split_dir" \
    --out "$out/real-derived.jsonl" \
    --exclude "$train" --exclude "$dev" --exclude "$test" \
    --exclude "$hard_eval" --exclude "$challenge"
  "$python_bin" "$repo_root/tools/validate_v6_foundation.py" \
    "$out/real-derived.jsonl" --require-approved
  "$python_bin" "$repo_root/tools/split_v6_auto_real.py" \
    --input "$out/real-derived.jsonl" --out-dir "$out/real-splits"
  train_files+=("$out/real-splits/train.jsonl")
  dev_files+=("$out/real-splits/dev.jsonl")
  test_files+=("$out/real-splits/test.jsonl")
fi

"$python_bin" "$repo_root/tools/train_v6_edit_tagger.py" \
  --train "${train_files[@]}" --dev "${dev_files[@]}" --test "${test_files[@]}" \
  --out "$out" --epochs "$epochs" --threads 1 --model "$model" \
  --min-available-mb "$min_available_mb"
"$python_bin" "$repo_root/tools/eval_v6_tagger.py" \
  --model-dir "$out" --data "$challenge" --out "$challenge_report" \
  --min-available-mb "$min_available_mb"
"$python_bin" "$repo_root/tools/eval_v6_tagger.py" \
  --model-dir "$out" --data "$hard_eval" --out "$hard_report" \
  --min-available-mb "$min_available_mb"

"$python_bin" -c 'import json,sys; d={name:json.load(open(path)) for name,path in zip(("challenge","hard_eval"),sys.argv[1:3])}; print(json.dumps({name:{"rows":v["rows"],"exact":v["exact"],"exact_rate":v["exact_rate"],"protected_failures":v["protected_failures"],"evaluated_row_ids_sha256":v["evaluated_row_ids_sha256"]} for name,v in d.items()},sort_keys=True))' "$challenge_report" "$hard_report"
