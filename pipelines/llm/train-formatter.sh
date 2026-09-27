#!/usr/bin/env bash
# Shared formatter training entry point. Dataset text is read from files, never argv.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)

exec python3 "$repo_root/tools/train_v5_formatter_contract.py" "$@"
