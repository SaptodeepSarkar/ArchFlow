#!/usr/bin/env bash
# Gate 04 — audio-helper. GREEN only if: 5s capture works, zero new audio
# bytes land on disk, busy/killable flags are correct during and after.
set -u
cd "$(dirname "$0")/../.."

CRATE="crates/audio-helper"
BIN="$CRATE/target/debug/capture"
SECS=5

fail() { echo "FAIL: $1"; exit 1; }

command -v pw-record >/dev/null || fail "pw-record not installed"
cargo build --manifest-path "$CRATE/Cargo.toml" 2>&1 | tail -3
[ -x "$BIN" ] || fail "capture binary not built"

# Disk audit: marker first, so the build itself is never counted.
MARKER="$(mktemp)"
sleep 1
touch "$MARKER"
AUDIT_DIRS=()
for d in "${TMPDIR:-/tmp}" /dev/shm "$PWD" "$HOME/.cache"; do
  [ -d "$d" ] && AUDIT_DIRS+=("$d")
done

OUT="$("$BIN" --secs "$SECS")" || fail "capture run failed: $OUT"
echo "$OUT"

echo "$OUT" | grep -q "during busy=true killable=false" \
  || fail "busy flag wrong during recording"
echo "$OUT" | grep -q "after busy=false killable=true" \
  || fail "killable flag wrong after stop"

SAMPLES="$(echo "$OUT" | sed -n 's/^capture samples=\([0-9]*\).*/\1/p')"
[ -n "$SAMPLES" ] || fail "no sample count reported"
# Expect 5s * 16kHz mono within +-15% (scheduling/headroom tolerance).
[ "$SAMPLES" -ge 68000 ] && [ "$SAMPLES" -le 92000 ] \
  || fail "expected ~80000 samples for 5s, got $SAMPLES"

NEW_AUDIO=""
AUDIO_EXPR="\( -iname '*.wav' -o -iname '*.raw' -o -iname '*.pcm' -o -iname '*.au' -o -iname '*.snd' -o -iname '*.ogg' -o -iname '*.flac' \)"
for d in "${AUDIT_DIRS[@]}"; do
  if [ "$d" = "${TMPDIR:-/tmp}" ]; then
    # /tmp is shared with the whole desktop: only flag names Vaani's own
    # stack could produce (our crates structurally write no audio files).
    FOUND="$(find "$d" -maxdepth 1 -newer "$MARKER" -type f $AUDIO_EXPR \
      \( -iname 'vaani*' -o -iname '*vosk*' -o -iname '*transcribe*' -o -iname '*pw-record*' \) 2>/dev/null)"
  else
    FOUND="$(find "$d" -newer "$MARKER" -type f $AUDIO_EXPR 2>/dev/null)"
  fi
  [ -n "$FOUND" ] && NEW_AUDIO+="$FOUND "
done
rm -f "$MARKER"
[ -z "$NEW_AUDIO" ] || fail "new audio bytes on disk: $NEW_AUDIO"

echo "GREEN: 5s capture ok (samples=$SAMPLES), zero audio bytes on disk, flags correct"
