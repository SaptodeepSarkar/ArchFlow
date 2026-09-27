#!/usr/bin/env bash
# Validate the checked-out shared formatter data when a prepared dataset exists.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
formatter_data="$repo_root/data/shared/llm/prepared/foundation.jsonl"

if [[ -f "$formatter_data" ]]; then
  exec python3 "$repo_root/tools/validate_v6_foundation.py" "$formatter_data"
fi

printf '%s\n' 'No prepared shared formatter dataset found; nothing to validate.'
