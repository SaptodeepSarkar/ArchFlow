#!/usr/bin/env bash
# Colab setup: system deps, python deps, then download + sha256-verify + unpack the data bundle.
# Env: VAANI_DATA_URL (Drive id or https), VAANI_DATA_SHA256, VAANI_DATA_DIR.
set -euo pipefail

DATA_URL="${VAANI_DATA_URL:-}"
DATA_SHA="${VAANI_DATA_SHA256:-}"
DATA_SHA="${DATA_SHA%% *}"  # accept a full sha256sum line
DATA_DIR="${VAANI_DATA_DIR:-/content/vaani-data}"
ARCHIVE="${VAANI_DATA_ARCHIVE:-$(dirname "$DATA_DIR")/vaani-v8-data.tar.zst}"

echo "=== Vaani V8 bootstrap"
echo "data_dir=$DATA_DIR"

missing=()
for bin in ffmpeg tar zstd curl git cmake; do
  command -v "$bin" >/dev/null 2>&1 || missing+=("$bin")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "apt: installing ${missing[*]}"
  apt-get update -qq
  apt-get install -y -qq "${missing[@]}"
fi

echo "=== python deps"
python3 -m pip install -q --upgrade "transformers>=4.46,<5" "tokenizers>=0.20" \
  jiwer bitsandbytes ctranslate2 gdown
python3 - <<'PY'
import torch
if not torch.cuda.is_available():
    raise SystemExit("no CUDA: select a GPU runtime (Runtime > Change runtime type > T4)")
print(f"torch {torch.__version__} on {torch.cuda.get_device_name(0)}")
PY

if [[ -z "$DATA_URL" ]]; then
  echo "VAANI_DATA_URL not set: skipping download, expecting $DATA_DIR to be populated."
else
  mkdir -p "$(dirname "$ARCHIVE")" "$DATA_DIR"
  if [[ -f "$ARCHIVE" ]]; then
    echo "=== reusing $ARCHIVE"
  elif [[ "$DATA_URL" =~ ^[A-Za-z0-9_-]{20,}$ ]]; then
    echo "=== gdown $DATA_URL"
    python3 -m gdown --fuzzy "$DATA_URL" -O "$ARCHIVE"
  else
    echo "=== curl $DATA_URL"
    curl -fL --retry 3 --retry-delay 5 -o "$ARCHIVE" "$DATA_URL"
  fi

  if [[ -z "$DATA_SHA" && -f "$ARCHIVE.sha256" ]]; then
    DATA_SHA="$(cut -d' ' -f1 "$ARCHIVE.sha256")"
  fi
  ACTUAL="$(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
  if [[ -n "$DATA_SHA" && "$ACTUAL" != "$DATA_SHA" ]]; then
    echo "sha256 mismatch: expected $DATA_SHA got $ACTUAL" >&2
    exit 1
  fi
  echo "=== sha256 ok ($ACTUAL)"

  tar --zstd -xf "$ARCHIVE" -C "$DATA_DIR"
fi

python3 - "$DATA_DIR" <<'PY'
import json, os, sys
root = sys.argv[1]
for split in ("train", "dev", "test"):
    for kind in ("stt", "formatter"):
        path = os.path.join(root, kind, f"{split}.jsonl")
        if not os.path.exists(path):
            raise SystemExit(f"missing {path}")
        with open(path) as f:
            count = sum(1 for line in f if line.strip())
        print(f"{kind}/{split}: {count} rows")
manifest = os.path.join(root, "manifest.json")
if os.path.exists(manifest):
    data = json.load(open(manifest))
    print(f"manifest: contract={data.get('contract_version')} created={data.get('created_at')}")
print(f"data ready: {root}")
PY
