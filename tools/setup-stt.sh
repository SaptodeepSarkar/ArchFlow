#!/usr/bin/env bash
# One-shot local STT setup: pinned whisper.cpp CPU build + base model.
# Fully user-local (no sudo, no system upgrade, no dotfile edits).
# Weights download here at setup time — never bundled, never at package build.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIN="$(cat "$REPO_ROOT/native/worker/WHISPER_PIN" 2>/dev/null | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
PIN="${PIN:-v1.7.6}"
SRC="$REPO_ROOT/native/worker/upstream"
BUILD="$REPO_ROOT/native/worker/build"
MODEL="${XDG_DATA_HOME:-$HOME/.local/share}/vaani/models/base.bin"

if [ ! -x "$HOME/.local/bin/whisper-cli" ]; then
  echo "==> whisper.cpp $PIN (clone + CPU build, a few minutes)..."
  if [ ! -d "$SRC" ]; then
    git clone --branch "$PIN" --depth 1 https://github.com/ggml-org/whisper.cpp "$SRC"
  fi
  cmake -S "$SRC" -B "$BUILD" -DWHISPER_BUILD_TESTS=OFF -DCMAKE_BUILD_TYPE=Release
  cmake --build "$BUILD" -j"$(nproc)"
  mkdir -p "$HOME/.local/bin"
  install -m755 "$BUILD/bin/whisper-cli" "$HOME/.local/bin/whisper-cli"
  if [ -x "$BUILD/bin/vad-speech-segments" ]; then
    install -m755 "$BUILD/bin/vad-speech-segments" "$HOME/.local/bin/vad-speech-segments"
  fi
else
  echo "==> whisper-cli already present, skipping build"
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
"$HOME/.local/bin/whisper-cli" -m "$MODEL" \
  -f "$SRC/samples/jfk.wav" -otxt -of /tmp/vaani-verify -t 4 -l en 2>/dev/null
echo "--- transcript:"; cat /tmp/vaani-verify.txt; rm -f /tmp/vaani-verify.txt
echo "OK: STT ready. Restart the service: systemctl --user restart vaanid"
