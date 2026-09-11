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
PIN="$(cat "$REPO_ROOT/native/worker/WHISPER_PIN" 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
PIN="${PIN:-v1.7.6}"
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

if [ ! -x "$HOME/.local/bin/$TARGET_NAME" ]; then
  echo "==> whisper.cpp $PIN build ($([ "$USE_CUDA" -eq 1 ] && echo CUDA || echo CPU), a few minutes)..."
  if [ ! -d "$SRC" ]; then
    git clone --branch "$PIN" --depth 1 https://github.com/ggml-org/whisper.cpp "$SRC"
  fi
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

if [ ! -f "$MODEL" ]; then
  echo "==> base model (~148 MB)..."
  python3 "$REPO_ROOT/tools/model-setup.py" --model base
else
  echo "==> base model already present, skipping download"
fi

echo "==> verifying on the upstream speech sample..."
"$HOME/.local/bin/$TARGET_NAME" -m "$MODEL" \
  -f "$SRC/samples/jfk.wav" -otxt -of /tmp/vaani-verify -t 4 -l en 2>/dev/null
echo "--- transcript:"; cat /tmp/vaani-verify.txt; rm -f /tmp/vaani-verify.txt
echo "OK: $TARGET_NAME ready. Restart the service: systemctl --user restart vaanid"
