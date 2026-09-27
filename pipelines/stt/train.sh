#!/usr/bin/env bash
# Shared STT training entry point. Audio remains in files referenced by a manifest.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

if [[ $# -eq 0 ]]; then
  printf '%s\n' 'usage: pipelines/stt/train.sh --manifest PATH --model PATH --out PATH [trainer options]' >&2
  exit 64
fi

exec python3 "$repo_root/tools/train_v5_whisper_lora.py" --streaming "$@"
