#!/usr/bin/env bash
# One-shot local STT setup: pinned whisper.cpp CPU build + base model.
# Fully user-local (no sudo, no system upgrade, no dotfile edits).
# Weights download here at setup time — never bundled, never at package build.
set -euo pipefail
USE_CUDA=0
if [ "${1:-}" = "--cuda" ]; then
  USE_CUDA=1
elif [ -n "${1:-}" ]; then
  echo "usage: $0 [--cuda]" >&2
  exit 2
fi
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIN="$(cat "$REPO_ROOT/native/worker/WHISPER_PIN" 2>/dev/null | grep -oE '[0-9a-f]{40}' | head -1)"
PIN="${PIN:-a8d002cfd879315632a579e73f0148d06959de36}"
SRC="$REPO_ROOT/native/worker/upstream"
BUILD="$REPO_ROOT/native/worker/build"
if [ "$USE_CUDA" -eq 1 ]; then
  BUILD="$REPO_ROOT/native/worker/build-cuda"
fi
MODEL="${XDG_DATA_HOME:-$HOME/.local/share}/vaani/models/base.bin"

TARGET_NAME="whisper-cli"
if [ "$USE_CUDA" -eq 1 ]; then
  TARGET_NAME="whisper-cli-cuda"
fi

if [ ! -d "$SRC" ]; then
  mkdir -p "$SRC"
  git -C "$SRC" init -q
fi
git -C "$SRC" fetch --depth 1 https://github.com/ggml-org/whisper.cpp "$PIN"
git -C "$SRC" checkout --detach FETCH_HEAD

if [ ! -x "$HOME/.local/bin/$TARGET_NAME" ]; then
  echo "==> whisper.cpp $PIN build ($([ "$USE_CUDA" -eq 1 ] && echo CUDA || echo CPU), a few minutes)..."
  CMAKE_ARGS=(-DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF)
  if [ "$USE_CUDA" -eq 1 ]; then
    if ! command -v nvcc >/dev/null; then
      echo "CUDA toolkit not found (nvcc is required)." >&2
      exit 1
    fi
    CMAKE_ARGS+=(-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86)
  fi
  cmake -S "$SRC" -B "$BUILD" "${CMAKE_ARGS[@]}"
  cmake --build "$BUILD" -j"$(nproc)"
  mkdir -p "$HOME/.local/bin"
  install -m755 "$BUILD/bin/whisper-cli" "$HOME/.local/bin/$TARGET_NAME"
  if [ "$USE_CUDA" -eq 0 ] && [ -x "$BUILD/bin/vad-speech-segments" ]; then
    install -m755 "$BUILD/bin/vad-speech-segments" "$HOME/.local/bin/vad-speech-segments"
  fi
else
  echo "==> $TARGET_NAME already present, skipping build"
fi

# Silero VAD model (tiny, ~1 MB) for speech gating + end-of-speech detection.
VAD_MODEL="${XDG_DATA_HOME:-$HOME/.local/share}/vaani/models/ggml-silero-v5.1.2.bin"
if [ ! -f "$VAD_MODEL" ]; then
  echo "==> silero VAD model..."
  bash "$SRC/models/download-vad-model.sh" silero-v5.1.2 "$(dirname "$VAD_MODEL")"
else
  echo "==> silero VAD model already present, skipping download"
fi

echo "==> verifying base model (~148 MB)..."
python3 "$REPO_ROOT/tools/model-setup.py" --model base

echo "==> verifying on the upstream speech sample..."
verify_dir="$(mktemp -d "${TMPDIR:-/tmp}/vaani-verify.XXXXXX")"
trap 'rm -rf -- "$verify_dir"' EXIT
"$HOME/.local/bin/$TARGET_NAME" -m "$MODEL" \
  -f "$SRC/samples/jfk.wav" -otxt -of "$verify_dir/transcript" -t 4 -l en 2>/dev/null
echo "--- transcript:"; cat "$verify_dir/transcript.txt"
echo "OK: $TARGET_NAME ready. Restart the service: systemctl --user restart vaanid"
