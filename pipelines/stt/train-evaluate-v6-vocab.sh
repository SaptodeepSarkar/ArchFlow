#!/usr/bin/env bash
# Automatically gated Whisper-small vocabulary experiment.
# Requires a CUDA training host; artifacts and private evaluation rows stay out
# of Git. No per-row human review is part of this workflow.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${PYTHON:-python3}
if ! "$python_bin" -c 'import torch, transformers, peft' >/dev/null 2>&1 \
    && [[ -x "$repo_root/training/cleanup-llm/.venv/bin/python" ]]; then
  python_bin="$repo_root/training/cleanup-llm/.venv/bin/python"
fi
train_manifest= dev_manifest= synthetic_manifest= model= out= eval_device=cuda
resume_checkpoint=
supplemental_train_manifests=()
supplemental_dev_manifests=()
supplemental_sqlite_train_manifests=()
supplemental_sqlite_dev_manifests=()
sqlite_source_fractions=()
steps=1500 sample_weight=8 sqlite_sample_fraction=0 holdout_percent=20 split_strategy=seen-term-context

usage() {
  printf '%s\n' 'usage: train-evaluate-v6-vocab.sh --train-manifest PATH [--supplemental-train-manifest PATH ...] --dev-manifest PATH [--supplemental-dev-manifest PATH ...] --synthetic-manifest PATH [--supplemental-sqlite-train-manifest PATH ... --sqlite-source-fraction FRACTION ...] [--supplemental-sqlite-dev-manifest PATH ...] --model PATH --out PATH [--resume-training-checkpoint PATH] [--steps N] [--sample-weight N] [--sqlite-sample-fraction 0..0.99] [--holdout-percent N] [--split-strategy seen-term-context|term-disjoint] [--eval-device cuda|cpu]'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --train-manifest) train_manifest=$2; shift 2 ;;
    --supplemental-train-manifest) supplemental_train_manifests+=("$2"); shift 2 ;;
    --supplemental-dev-manifest) supplemental_dev_manifests+=("$2"); shift 2 ;;
    --supplemental-sqlite-train-manifest) supplemental_sqlite_train_manifests+=("$2"); shift 2 ;;
    --supplemental-sqlite-dev-manifest) supplemental_sqlite_dev_manifests+=("$2"); shift 2 ;;
    --sqlite-source-fraction) sqlite_source_fractions+=("$2"); shift 2 ;;
    --dev-manifest) dev_manifest=$2; shift 2 ;;
    --synthetic-manifest) synthetic_manifest=$2; shift 2 ;;
    --model) model=$2; shift 2 ;;
    --out) out=$2; shift 2 ;;
    --resume-training-checkpoint) resume_checkpoint=$2; shift 2 ;;
    --steps) steps=$2; shift 2 ;;
    --sample-weight) sample_weight=$2; shift 2 ;;
    --sqlite-sample-fraction) sqlite_sample_fraction=$2; shift 2 ;;
    --holdout-percent) holdout_percent=$2; shift 2 ;;
    --split-strategy) split_strategy=$2; shift 2 ;;
    --eval-device) eval_device=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
done

for name in train_manifest dev_manifest synthetic_manifest model out; do
  [[ -n "${!name}" ]] || { usage >&2; exit 64; }
done
for path in "$train_manifest" "$dev_manifest" "$synthetic_manifest" "$model"; do
  [[ -e "$path" ]] || { printf 'missing input: %s\n' "$path" >&2; exit 66; }
done
for path in "${supplemental_train_manifests[@]}"; do
  [[ -f "$path" ]] || { printf 'missing supplemental training manifest: %s\n' "$path" >&2; exit 66; }
done
for path in "${supplemental_dev_manifests[@]}"; do
  [[ -f "$path" ]] || { printf 'missing supplemental development manifest: %s\n' "$path" >&2; exit 66; }
done
for path in "${supplemental_sqlite_train_manifests[@]}"; do
  [[ -f "$path" ]] || { printf 'missing supplemental SQLite training manifest: %s\n' "$path" >&2; exit 66; }
done
for path in "${supplemental_sqlite_dev_manifests[@]}"; do
  [[ -f "$path" ]] || { printf 'missing supplemental SQLite development manifest: %s\n' "$path" >&2; exit 66; }
done
[[ "$eval_device" == cuda || "$eval_device" == cpu ]] || { usage >&2; exit 64; }
[[ "$split_strategy" == seen-term-context || "$split_strategy" == term-disjoint ]] || { usage >&2; exit 64; }
[[ "$steps" =~ ^[1-9][0-9]*$ && "$holdout_percent" =~ ^([1-9]|[1-4][0-9])$ ]] || {
  printf 'steps and holdout percent must be positive integers (holdout 1..49)\n' >&2; exit 64;
}
[[ "$sample_weight" =~ ^[0-9]+([.][0-9]+)?$ ]] || { printf 'invalid sample weight\n' >&2; exit 64; }
[[ "$sqlite_sample_fraction" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
  printf 'invalid SQLite sampling fraction\n' >&2; exit 64;
}
"$python_bin" -c 'import sys; x=float(sys.argv[1]); sys.exit(0 if 0 <= x < 1 else 1)' \
  "$sqlite_sample_fraction" || { printf 'SQLite sampling fraction must be below 1\n' >&2; exit 64; }
sqlite_sample_fraction_active=0
if "$python_bin" -c 'import sys; sys.exit(0 if float(sys.argv[1]) > 0 else 1)' \
    "$sqlite_sample_fraction"; then
  sqlite_sample_fraction_active=1
fi
if ((${#sqlite_source_fractions[@]})); then
  expected_sqlite_sources=$((1 + ${#supplemental_sqlite_train_manifests[@]}))
  ((${#sqlite_source_fractions[@]} == expected_sqlite_sources)) || {
    printf 'pass exactly one --sqlite-source-fraction per SQLite training manifest\n' >&2; exit 64;
  }
  ((sqlite_sample_fraction_active == 0)) || {
    printf 'use per-source fractions or the combined SQLite fraction, not both\n' >&2; exit 64;
  }
  "$python_bin" -c 'import math,sys; x=list(map(float,sys.argv[1:])); sys.exit(0 if all(math.isfinite(v) and 0<v<1 for v in x) and sum(x)<1 else 1)' \
    "${sqlite_source_fractions[@]}" || { printf 'per-source fractions must be positive and sum below 1\n' >&2; exit 64; }
fi

# Training is CUDA-only. Check before creating the output directory or writing
# a term split so a machine with a dead/missing driver leaves no partial run.
if ! "$python_bin" -c 'import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)' >/dev/null 2>&1; then
  printf 'CUDA is unavailable to %s; V6 Whisper training was not started and no outputs were created.\n' "$python_bin" >&2
  exit 69
fi

out_abs=$(realpath -m "$out")
case "$out_abs/" in
  "$repo_root/"*) printf 'model/evaluation outputs must stay outside Git: %s\n' "$out_abs" >&2; exit 73 ;;
esac
if [[ -n "$resume_checkpoint" ]]; then
  resume_abs=$(realpath -e "$resume_checkpoint") || { printf 'resume checkpoint does not exist\n' >&2; exit 66; }
  case "$resume_abs/" in
    "$out_abs/training/"*) ;;
    *) printf 'resume checkpoint must be inside this experiment training directory: %s\n' "$resume_abs" >&2; exit 73 ;;
  esac
  [[ -f "$resume_abs/trainer_state.json" ]] || { printf 'resume checkpoint is incomplete\n' >&2; exit 66; }
  [[ -f "$out_abs/vocab-split/heldout.jsonl" && -f "$out_abs/vocab-split/train.sqlite3" ]] || {
    printf 'resume requires the original vocabulary split beside the training directory\n' >&2; exit 66;
  }
  [[ -d "$out_abs/training" ]] || { printf 'resume training directory is missing\n' >&2; exit 66; }
  for report in "$out_abs"/base-*.jsonl "$out_abs"/candidate-*.jsonl "$out_abs"/comparison-*.json; do
    [[ ! -e "$report" ]] || { printf 'refusing resume after evaluation artifacts exist: %s\n' "$report" >&2; exit 73; }
  done
  current_step=$("$python_bin" -c 'import json,sys; print(json.load(open(sys.argv[1]))["global_step"])' "$resume_abs/trainer_state.json")
  [[ "$current_step" =~ ^[0-9]+$ && "$current_step" -lt "$steps" ]] || {
    printf 'checkpoint step must be below requested final step (%s)\n' "$steps" >&2; exit 64;
  }
else
  [[ ! -e "$out_abs" ]] || { printf 'refusing to overwrite experiment output: %s\n' "$out_abs" >&2; exit 73; }
fi

(
  cd "$repo_root"
  "$python_bin" -m unittest tests.test_audit_v6_stt_sampling \
    tests.test_split_v6_synthetic_vocab \
    tests.test_v6_synthetic_vocab_provenance \
    tests.test_compare_v6_whisper_evals tests.test_v6_linux_ct2_eval \
    tests.test_whisper_training_collator
  "$python_bin" -m py_compile tools/train_v6_stt.py tools/eval_v5_whisper_adapter.py \
    tools/split_v6_synthetic_vocab.py tools/compare_v6_whisper_evals.py \
    tools/audit_v6_stt_sampling.py tools/build_v6_synthetic_vocab_audio.py \
    tools/v6_synthetic_vocab_provenance.py
)

mkdir -p "$(dirname "$out_abs")"
if [[ -z "$resume_checkpoint" ]]; then
  "$python_bin" "$repo_root/tools/split_v6_synthetic_vocab.py" \
    --manifest "$synthetic_manifest" --out-dir "$out_abs/vocab-split" \
    --holdout-percent "$holdout_percent" --strategy "$split_strategy"
fi

# The base must be the clean, locally cached Whisper checkpoint. Only the
# generated training partition is supplied to the optimizer. The default
# context-held-out strategy keeps every vocabulary term in train while keeping
# the scored sentence frame/audio examples held out. Term-disjoint transfer
# remains available only as an optional diagnostic.
# Keep Trainer's logging_steps visible in supervised/non-TTY sessions too;
# otherwise buffered stdout makes a long GPU run appear silent until exit.
training_manifests=(--manifest "$train_manifest")
for path in "${supplemental_train_manifests[@]}"; do
  training_manifests+=(--manifest "$path")
done
sqlite_sampling_args=()
resume_args=()
if [[ -n "$resume_checkpoint" ]]; then
  resume_args=(--resume-from-checkpoint "$resume_checkpoint")
fi
if ((sqlite_sample_fraction_active)); then
  sqlite_sampling_args=(--sqlite-sample-fraction "$sqlite_sample_fraction")
fi
sqlite_training_manifests=(--sqlite-manifest "$out_abs/vocab-split/train.sqlite3")
for path in "${supplemental_sqlite_train_manifests[@]}"; do
  sqlite_training_manifests+=(--sqlite-manifest "$path")
done
for fraction in "${sqlite_source_fractions[@]}"; do
  sqlite_training_manifests+=(--sqlite-source-fraction "$fraction")
done
sampling_audit_args=(--steps "$steps")
if ((${#sqlite_source_fractions[@]})); then
  for path in "$out_abs/vocab-split/train.sqlite3" "${supplemental_sqlite_train_manifests[@]}"; do
    sampling_audit_args+=(--sqlite-manifest "$path")
  done
  for fraction in "${sqlite_source_fractions[@]}"; do
    sampling_audit_args+=(--source-fraction "$fraction")
  done
elif ((sqlite_sample_fraction_active)); then
  for path in "$out_abs/vocab-split/train.sqlite3" "${supplemental_sqlite_train_manifests[@]}"; do
    sampling_audit_args+=(--sqlite-manifest "$path")
  done
  sampling_audit_args+=(--combined-fraction "$sqlite_sample_fraction")
fi
if ((${#sampling_audit_args[@]} > 2)); then
  "$python_bin" "$repo_root/tools/audit_v6_stt_sampling.py" \
    "${sampling_audit_args[@]}" --report "$out_abs/sampling-exposure-audit.json"
fi
PYTHONUNBUFFERED=1 "$python_bin" "$repo_root/tools/train_v6_stt.py" --pre-split --streaming \
  "${training_manifests[@]}" \
  "${sqlite_training_manifests[@]}" \
  --sqlite-sample-weight "$sample_weight" "${sqlite_sampling_args[@]}" --model "$model" \
  --out "$out_abs/training" --steps "$steps" --batch-size 2 \
  "${resume_args[@]}" \
  --grad-accum 8 --learning-rate 1e-5 --no-augment

for suite in vocab-heldout ami-dev; do
  source_manifest="$out_abs/vocab-split/heldout.jsonl"
  [[ "$suite" != ami-dev ]] || source_manifest=$dev_manifest
  for protocol in base candidate; do
    adapter_args=()
    [[ "$protocol" != candidate ]] || adapter_args=(--adapter "$out_abs/training/adapter")
    "$python_bin" "$repo_root/tools/eval_v5_whisper_adapter.py" \
      --report "$source_manifest" --model "$model" "${adapter_args[@]}" \
      --out "$out_abs/$protocol-$suite.jsonl" --limit 0 --beams 5 \
      --batch-size 2 --device "$eval_device"
  done
done

# Optional independent-domain development suites use identical base/candidate
# decoding and aggregate-only reports. They have no minimum vocabulary support
# requirement; their role is to catch broad regressions, not tune on public test.
supplemental_reports=()
for index in "${!supplemental_dev_manifests[@]}"; do
  suite="supplemental-dev-$((index + 1))"
  source_manifest=${supplemental_dev_manifests[$index]}
  for protocol in base candidate; do
    adapter_args=()
    [[ "$protocol" != candidate ]] || adapter_args=(--adapter "$out_abs/training/adapter")
    "$python_bin" "$repo_root/tools/eval_v5_whisper_adapter.py" \
      --report "$source_manifest" --model "$model" "${adapter_args[@]}" \
      --out "$out_abs/$protocol-$suite.jsonl" --limit 0 --beams 5 \
      --batch-size 2 --device "$eval_device"
  done
  "$python_bin" "$repo_root/tools/compare_v6_whisper_evals.py" \
    --base "$out_abs/base-$suite.jsonl" \
    --candidate "$out_abs/candidate-$suite.jsonl" \
    --report "$out_abs/comparison-$suite.json" \
    --suite "$suite" \
    --minimum-wer-improvement 0 --maximum-protected-term-drop 0 \
    --minimum-protected-term-support 0
  supplemental_reports+=("$out_abs/comparison-$suite.json")
done
for index in "${!supplemental_sqlite_dev_manifests[@]}"; do
  suite="supplemental-sqlite-dev-$((index + 1))"
  source_manifest=${supplemental_sqlite_dev_manifests[$index]}
  for protocol in base candidate; do
    adapter_args=()
    [[ "$protocol" != candidate ]] || adapter_args=(--adapter "$out_abs/training/adapter")
    "$python_bin" "$repo_root/tools/eval_v5_whisper_adapter.py" \
      --report "$source_manifest" --model "$model" "${adapter_args[@]}" \
      --out "$out_abs/$protocol-$suite.jsonl" --limit 0 --beams 5 \
      --batch-size 2 --device "$eval_device"
  done
  "$python_bin" "$repo_root/tools/compare_v6_whisper_evals.py" \
    --base "$out_abs/base-$suite.jsonl" \
    --candidate "$out_abs/candidate-$suite.jsonl" \
    --report "$out_abs/comparison-$suite.json" \
    --suite "$suite" \
    --minimum-wer-improvement 0 --maximum-protected-term-drop 0 \
    --minimum-protected-term-support 0
  supplemental_reports+=("$out_abs/comparison-$suite.json")
done

# The seen-term/context-holdout suite requires non-regressing WER and at least
# 99% protected-term accuracy on sentence frames excluded from training. AMI
# dev requires non-regression in both WER and protected terms.
"$python_bin" "$repo_root/tools/compare_v6_whisper_evals.py" \
  --base "$out_abs/base-vocab-heldout.jsonl" \
  --candidate "$out_abs/candidate-vocab-heldout.jsonl" \
  --report "$out_abs/comparison-vocab-heldout.json" \
  --suite vocab-heldout \
  --minimum-wer-improvement 0 --maximum-protected-term-drop 0 \
  --minimum-protected-term-support 50 --minimum-protected-term-accuracy 99
"$python_bin" "$repo_root/tools/compare_v6_whisper_evals.py" \
  --base "$out_abs/base-ami-dev.jsonl" --candidate "$out_abs/candidate-ami-dev.jsonl" \
  --report "$out_abs/comparison-ami-dev.json" \
  --suite ami-dev \
  --minimum-wer-improvement 0 --maximum-protected-term-drop 0 \
  --minimum-protected-term-support 1

"$python_bin" -c 'import json,sys; from pathlib import Path; reports=[Path(p) for p in sys.argv[1:]]; results=[json.loads(p.read_text()) for p in reports]; print(json.dumps({"all_gates_passed":all(x["promotion_eligible"] for x in results),"suites":[{"suite":x["suite"] if "suite" in x else p.stem,"promotion_eligible":x["promotion_eligible"]} for p,x in zip(reports,results)]},sort_keys=True)); sys.exit(0 if all(x["promotion_eligible"] for x in results) else 1)' \
  "$out_abs/comparison-vocab-heldout.json" "$out_abs/comparison-ami-dev.json" \
  "${supplemental_reports[@]}"

printf 'Candidate and aggregate-only reports saved outside Git at %s\n' "$out_abs"
