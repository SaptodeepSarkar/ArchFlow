#!/usr/bin/env bash
# Run every paired V5/V6 formatter qualification suite, even if a gate fails.
set -uo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${PYTHON:-python3}
synthetic_dir= real_dir= challenge= independent_challenge= hard_eval= model= adapter= v5_adapter= out=
usage() {
  printf '%s\n' 'usage: evaluate-v6-seq2seq-all.sh --synthetic-dir PATH --real-dir PATH --challenge PATH --independent-challenge PATH --hard-eval PATH --model PATH --adapter PATH --v5-adapter PATH --out NEW_OUTSIDE_REPO_DIR'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --synthetic-dir) synthetic_dir=$2; shift 2 ;;
    --real-dir) real_dir=$2; shift 2 ;;
    --challenge) challenge=$2; shift 2 ;;
    --independent-challenge) independent_challenge=$2; shift 2 ;;
    --hard-eval) hard_eval=$2; shift 2 ;;
    --model) model=$2; shift 2 ;;
    --adapter) adapter=$2; shift 2 ;;
    --v5-adapter) v5_adapter=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

for name in synthetic_dir real_dir challenge independent_challenge hard_eval model adapter v5_adapter out; do
  [[ -n "${!name}" ]] || { usage >&2; exit 64; }
done
for path in "$synthetic_dir" "$real_dir" "$challenge" "$independent_challenge" "$hard_eval" "$model" "$adapter" "$v5_adapter"; do
  [[ -e "$path" ]] || { printf 'missing input: %s\n' "$path" >&2; exit 66; }
done
for split in test; do
  [[ -f "$synthetic_dir/$split.jsonl" && -f "$real_dir/$split.jsonl" ]] || {
    printf 'missing %s split under synthetic or real directory\n' "$split" >&2
    exit 66
  }
done
out_abs=$(realpath -m "$out")
case "$out_abs/" in
  "$repo_root/"*) printf 'reports must stay outside the Git worktree: %s\n' "$out_abs" >&2; exit 73 ;;
esac
[[ ! -e "$out_abs" ]] || { printf 'refusing to overwrite report directory: %s\n' "$out_abs" >&2; exit 73; }
mkdir -p "$out_abs" || exit 73

failures=()
eval_script="$repo_root/tools/eval_v6_seq2seq.py"
compare_script="$repo_root/tools/compare_v6_seq2seq.py"

run_suite() {
  local suite=$1
  shift
  local v5_report="$out_abs/v5-$suite.json"
  local v6_report="$out_abs/v6-$suite.json"
  local compare_report="$out_abs/comparison-$suite.json"
  local -a data_args=("$@")

  if ! "$python_bin" "$eval_script" --model "$model" --adapter "$adapter" \
      --protocol v6 --data "${data_args[@]}" --report "$v6_report"; then
    failures+=("$suite:v6-evaluation")
  fi
  if ! "$python_bin" "$eval_script" --model "$model" --adapter "$v5_adapter" --protocol v5 \
      --data "${data_args[@]}" --report "$v5_report"; then
    failures+=("$suite:v5-evaluation")
  fi
  if [[ -s "$v5_report" && -s "$v6_report" ]]; then
    local -a compare_args=(--v5 "$v5_report" --v6 "$v6_report" --suite "$suite"
      --report "$compare_report")
    case "$suite" in
      mixed-heldout-test) compare_args+=(--max-copy-fallback-rate 0.05) ;;
      real-test) compare_args+=(--max-copy-fallback-rate 0.01) ;;
    esac
    if ! "$python_bin" "$compare_script" "${compare_args[@]}"; then
      failures+=("$suite:promotion-gate")
    fi
  else
    failures+=("$suite:comparison-input-missing")
  fi
}

run_suite challenge "$challenge"
run_suite hard-eval "$hard_eval"
run_suite mixed-heldout-test "$synthetic_dir/test.jsonl" "$real_dir/test.jsonl"
run_suite real-test "$real_dir/test.jsonl"
run_suite independent-challenge "$independent_challenge"

printf 'Aggregate reports written to %s\n' "$out_abs"
if ((${#failures[@]})); then
  printf 'One or more suites failed execution or promotion gates: %s\n' "${failures[*]}" >&2
  exit 1
fi
printf 'All formatter evaluation suites passed.\n'
