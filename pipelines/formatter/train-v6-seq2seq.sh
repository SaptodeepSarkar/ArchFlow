#!/usr/bin/env bash
# Leak-excluded, aggregate-evaluated V6 constrained formatter candidate run.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${PYTHON:-python3}
usage() {
  printf '%s\n' 'usage: train-v6-seq2seq.sh --synthetic-dir PATH --real-dir PATH --replay PATH [--replay PATH ...] [--foundation-replay PATH ...] --challenge PATH --hard-eval PATH --model PATH --v5-adapter PATH --out PATH [--steps N] [--seed N] [--preflight-only] [--resume-from-checkpoint PATH]'
}

synthetic_dir= real_dir= challenge= hard_eval= model= v5_adapter= out= steps=3000 seed=42 resume_checkpoint= preflight_only=false
replays=()
foundation_replays=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --synthetic-dir) synthetic_dir=$2; shift 2 ;;
    --real-dir) real_dir=$2; shift 2 ;;
    --replay) replays+=("$2"); shift 2 ;;
    --foundation-replay) foundation_replays+=("$2"); shift 2 ;;
    --challenge) challenge=$2; shift 2 ;;
    --hard-eval) hard_eval=$2; shift 2 ;;
    --model) model=$2; shift 2 ;;
    --v5-adapter) v5_adapter=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    --steps) steps=$2; shift 2 ;;
    --seed) seed=$2; shift 2 ;;
    --preflight-only) preflight_only=true; shift ;;
    --resume-from-checkpoint) resume_checkpoint=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

for name in synthetic_dir real_dir challenge hard_eval model v5_adapter out; do
  [[ -n "${!name}" ]] || { usage >&2; exit 64; }
done
(( ${#replays[@]} > 0 )) || { usage >&2; exit 64; }
for path in "$synthetic_dir" "$real_dir" "$challenge" "$hard_eval" "$model" "$v5_adapter" "${replays[@]}" "${foundation_replays[@]}"; do
  [[ -e "$path" ]] || { printf 'missing input: %s\n' "$path" >&2; exit 66; }
done
for split in train dev test; do
  [[ -f "$synthetic_dir/$split.jsonl" && -f "$real_dir/$split.jsonl" ]] || {
    printf 'missing %s split under synthetic or real directory\n' "$split" >&2; exit 66;
  }
done
out_abs=$(realpath -m "$out")
case "$out_abs/" in
  "$repo_root/"*) printf 'model outputs must stay outside the Git worktree: %s\n' "$out_abs" >&2; exit 73 ;;
esac
if [[ -n "$resume_checkpoint" ]]; then
  resume_abs=$(realpath -e "$resume_checkpoint")
  case "$resume_abs" in
    "$out_abs/adapter/checkpoint-"*) ;;
    *) printf 'resume checkpoint must be inside %s/adapter: %s\n' "$out_abs" "$resume_abs" >&2; exit 73 ;;
  esac
  [[ -f "$resume_abs/trainer_state.json" ]] || { printf 'invalid Trainer checkpoint: %s\n' "$resume_abs" >&2; exit 66; }
  for report in "$out_abs"/v5-*.json "$out_abs"/v6-*.json "$out_abs"/comparison-*.json; do
    [[ ! -e "$report" ]] || { printf 'evaluation report already exists; refusing to overwrite: %s\n' "$report" >&2; exit 73; }
  done
else
  [[ ! -e "$out" ]] || { printf 'refusing to overwrite model candidate: %s\n' "$out" >&2; exit 73; }
fi

(
  cd "$repo_root"
  "$python_bin" -m unittest tests.test_render_v6_edit_plan tests.test_v6_hard_examples \
    tests.test_v6_seq2seq_data tests.test_formatter_protocol tests.test_compare_v6_seq2seq \
    tests.test_v6_eval_aggregate
  "$python_bin" -m py_compile tools/train_v6_seq2seq.py tools/eval_v6_seq2seq.py tools/compare_v6_seq2seq.py
  for path in "${foundation_replays[@]}"; do
    "$python_bin" tools/validate_v6_foundation.py "$path" --require-approved
  done
)

train=("$synthetic_dir/train.jsonl" "$real_dir/train.jsonl")
dev=("$synthetic_dir/dev.jsonl" "$real_dir/dev.jsonl")
resume_args=()
[[ -z "$resume_checkpoint" ]] || resume_args=(--resume-from-checkpoint "$resume_checkpoint")
replay_args=()
for path in "${replays[@]}"; do
  replay_args+=(--replay "$path")
done
for path in "${foundation_replays[@]}"; do
  replay_args+=(--replay "$path")
done

preflight_args=()
$preflight_only && preflight_args=(--preflight-only)
"$python_bin" "$repo_root/tools/train_v6_seq2seq.py" \
  --train "${train[@]}" --dev "${dev[@]}" "${replay_args[@]}" --replay-factor 3 \
  --exclude "$challenge" "$hard_eval" "$synthetic_dir/test.jsonl" "$real_dir/test.jsonl" \
  --model "$model" --out "$out/adapter" \
  --steps "$steps" --seed "$seed" --eval-steps 500 "${preflight_args[@]}" "${resume_args[@]}"

if $preflight_only; then
  exit 0
fi

mkdir -p "$out"

for suite in challenge hard-eval; do
  data=$challenge; [[ "$suite" == challenge ]] || data=$hard_eval
  "$python_bin" "$repo_root/tools/eval_v6_seq2seq.py" \
    --model "$model" --adapter "$out/adapter" --protocol v6 \
    --data "$data" --report "$out/v6-$suite.json"
  "$python_bin" "$repo_root/tools/eval_v6_seq2seq.py" \
    --model "$model" --adapter "$v5_adapter" --protocol v5 --data "$data" --report "$out/v5-$suite.json"
  "$python_bin" "$repo_root/tools/compare_v6_seq2seq.py" \
    --v5 "$out/v5-$suite.json" --v6 "$out/v6-$suite.json" \
    --suite "$suite" --report "$out/comparison-$suite.json"
done

test_data=("$synthetic_dir/test.jsonl" "$real_dir/test.jsonl")
for protocol in v6 v5; do
  adapter_args=(--adapter "$v5_adapter")
  [[ "$protocol" != v6 ]] || adapter_args=(--adapter "$out/adapter")
  "$python_bin" "$repo_root/tools/eval_v6_seq2seq.py" \
    --model "$model" --protocol "$protocol" "${adapter_args[@]}" \
    --data "${test_data[@]}" --report "$out/$protocol-heldout-test.json"
done
"$python_bin" "$repo_root/tools/compare_v6_seq2seq.py" \
  --v5 "$out/v5-heldout-test.json" --v6 "$out/v6-heldout-test.json" \
  --suite mixed-heldout-test --max-copy-fallback-rate 0.05 \
  --report "$out/comparison-heldout-test.json"

test_data=("$real_dir/test.jsonl")
for protocol in v6 v5; do
  adapter_args=(--adapter "$v5_adapter")
  [[ "$protocol" != v6 ]] || adapter_args=(--adapter "$out/adapter")
  "$python_bin" "$repo_root/tools/eval_v6_seq2seq.py" \
    --model "$model" --protocol "$protocol" "${adapter_args[@]}" \
    --data "${test_data[@]}" --report "$out/$protocol-real-test.json"
done
"$python_bin" "$repo_root/tools/compare_v6_seq2seq.py" \
  --v5 "$out/v5-real-test.json" --v6 "$out/v6-real-test.json" \
  --suite real-test --max-copy-fallback-rate 0.01 \
  --report "$out/comparison-real-test.json"

printf 'Candidate and aggregate reports saved outside Git at %s\n' "$out_abs"
