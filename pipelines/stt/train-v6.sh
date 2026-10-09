#!/usr/bin/env bash
# Train an experimental V6 Whisper-small adapter from an already group-split
# manifest. Start from an explicitly supplied clean base checkpoint; never
# inherit V5/V6 weights or an unreviewed corpus by default.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=${PYTHON:-python3}

if [[ $# -eq 0 ]]; then
  printf '%s\n' 'usage: pipelines/stt/train-v6.sh --manifest PATH --model PATH --out PATH [trainer options]' >&2
  exit 64
fi

exec "$python_bin" "$repo_root/tools/train_v6_stt.py" --streaming --pre-split "$@"
