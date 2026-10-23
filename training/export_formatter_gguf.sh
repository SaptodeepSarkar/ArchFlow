#!/usr/bin/env bash
# Export the averaged formatter to GGUF Q4_K_M with llama.cpp pinned to b11588.
set -euo pipefail

TAG="b11588"
MODEL=""
OUT=""
DRY_RUN=0
WORKDIR="${VAANI_LLAMA_DIR:-}"

usage() {
  echo "usage: $0 --model <hf-dir> --out <file.gguf> [--tag b11588] [--workdir DIR] [--dry-run]"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model|--ckpt) MODEL="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --workdir) WORKDIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "$MODEL" && -n "$OUT" ]] || { usage >&2; exit 2; }
[[ -f "$MODEL/config.json" ]] || { echo "not an HF model dir: $MODEL" >&2; exit 1; }

if [[ "$DRY_RUN" == "1" ]]; then
  python3 - "$MODEL" "$OUT" "$TAG" <<'PY'
import json, sys
model, out, tag = sys.argv[1:4]
json.dump({"source": model, "out": out, "tag": tag, "quantization": "Q4_K_M"},
          open(out + ".dry-run.json", "w"), indent=2)
print(f"[dry-run] would convert {model} -> {out} (Q4_K_M, llama.cpp {tag})")
PY
  exit 0
fi

WORKDIR="${WORKDIR:-$OUT.llama.cpp}"
SRC="$WORKDIR/llama.cpp"
if [[ ! -d "$SRC/.git" ]]; then
  mkdir -p "$WORKDIR"
  git clone --depth 1 --branch "$TAG" https://github.com/ggml-org/llama.cpp "$SRC"
fi

REQ="$SRC/requirements/requirements-convert_hf_to_gguf.txt"
[[ -f "$REQ" ]] || REQ="$SRC/requirements.txt"
python3 -m pip install -q -r "$REQ"
python3 -m pip install -q "$SRC/gguf-py"   # the pip gguf is older than the tag

TMP_F16="$OUT.f16.tmp.gguf"
PYTHONPATH="$SRC/gguf-py" python3 "$SRC/convert_hf_to_gguf.py" "$MODEL" \
  --outfile "$TMP_F16" --outtype f16

cmake -S "$SRC" -B "$SRC/build" -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_SERVER=OFF
cmake --build "$SRC/build" --target llama-quantize -j "$(nproc)"

QUANTIZE="$(find "$SRC/build" -type f -name llama-quantize | head -n 1)"
[[ -x "$QUANTIZE" ]] || { echo "llama-quantize not built" >&2; exit 1; }
"$QUANTIZE" "$TMP_F16" "$OUT" Q4_K_M
rm -f "$TMP_F16"
echo "exported $OUT (Q4_K_M, llama.cpp $TAG)"
