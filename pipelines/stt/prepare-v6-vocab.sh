#!/usr/bin/env bash
# Prepare expanded synthetic data; never start training or promote a model.
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${PYTHON:-python3}
manifest= frozen_heldout= out=
usage() {
  printf '%s\n' 'usage: prepare-v6-vocab.sh --manifest SQLITE --freeze-heldout PRIOR_JSONL --out NEW_OUTSIDE_REPO_DIR'
}
while (($#)); do
  case "$1" in
    --manifest) manifest=$2; shift 2 ;;
    --freeze-heldout) frozen_heldout=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done
[[ -f "$manifest" && -f "$frozen_heldout" && -n "$out" ]] || { usage >&2; exit 66; }
out_abs=$(realpath -m "$out")
case "$out_abs/" in
  "$repo_root/"*) printf 'prepared data must stay outside Git\n' >&2; exit 73 ;;
esac
[[ ! -e "$out_abs" ]] || { printf 'refusing existing prepared pack\n' >&2; exit 73; }
"$python_bin" "$repo_root/tools/validate_v6_synthetic_vocab_audio.py" --manifest "$manifest"
"$python_bin" "$repo_root/tools/split_v6_synthetic_vocab.py" \
  --manifest "$manifest" --out-dir "$out_abs" --strategy seen-term-context \
  --holdout-percent 20 --expected-terms 79 --expected-templates 12 \
  --expected-voices 2 --freeze-heldout "$frozen_heldout"
printf 'Prepared synthetic pack only; no training or promotion was performed.\n'
