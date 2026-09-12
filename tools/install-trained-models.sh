#!/usr/bin/env bash
# Install deployable locally-trained cleanup artifacts into the user data dir.
# Checkpoints, optimizer state, RNG state, and trainer logs are intentionally
# excluded. Model weights are not committed to this repository.
set -euo pipefail

src="${1:-training/cleanup-llm/output}"
src="$(cd "$src" && pwd)"
dest="${XDG_DATA_HOME:-$HOME/.local/share}/vaani/cleanup"
mkdir -p "$dest"

copy_model() {
  local name="$1"
  local from="$src/$name"
  local to="$dest/$name"
  if [[ ! -d "$from" ]]; then
    echo "missing: $from" >&2
    return 1
  fi
  rm -rf "$to"
  mkdir -p "$to"
  find "$from" -maxdepth 1 -type f \( \
    -name '*.json' -o -name '*.safetensors' -o -name '*.txt' -o \
    -name '*.jinja' -o -name 'LICENSE' -o -name 'README.md' \
  \) -exec cp -a {} "$to/" \;
  echo "installed $name -> $to"
}

copy_model base-model
copy_model llm-v1

echo "Cleanup models installed. Set cleanup.mode = \"stream\"; the daemon auto-detects these paths."
