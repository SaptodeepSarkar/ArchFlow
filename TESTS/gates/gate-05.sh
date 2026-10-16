#!/usr/bin/env bash
# Gate 05 — stt-stream. GREEN only if: fixture samples stream words with
# RTF under 0.3, and post-run VRAM is back to baseline with no backend left.
set -u
cd "$(dirname "$0")/../.."

BIN="target/debug/transcribe"
FIXDIR="TESTS/fixtures/audio"
RTF_LIMIT="0.3"

fail() { echo "FAIL: $1"; exit 1; }

command -v nvidia-smi >/dev/null || fail "nvidia-smi not found (gate runs on this RTX 3050 box only)"
nvidia-smi -L 2>/dev/null | grep -qi nvidia || fail "no NVIDIA dGPU listed"
BASELINE="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' ')"
echo "vram-baseline=${BASELINE}MiB (CPU engine: expect zero delta)"

# Self-heal workspace membership (siblings edit Cargo.toml concurrently).
grep -q 'crates/stt-manager' Cargo.toml || perl -0pi -e \
  's/("crates\/audio-helper",\n)/$1    "crates\/stt-manager",\n/' Cargo.toml
cargo build --manifest-path crates/stt-manager/Cargo.toml 2>&1 | tail -2
[ -x "$BIN" ] || fail "transcribe binary not built"

N=0
for wav in "$FIXDIR"/s1-hello.wav "$FIXDIR"/s2-hello.wav "$FIXDIR"/s3-hello-slow.wav \
           "$FIXDIR"/s4-hello-fast-loud.wav "$FIXDIR"/s5-hello-tail.wav; do
  [ -f "$wav" ] || fail "missing fixture $wav"
  OUT="$("./$BIN" --wav "$wav" 2>/tmp/vaani-gate-05-stderr.log)" || fail "$wav failed: $OUT"
  echo "$OUT" | grep -q "^device=DGpu " || fail "$wav: dGPU not picked on RTX 3050 box"
  echo "$OUT" | grep -q "during busy=true killable=false" || fail "$wav: busy flag wrong during decode"
  echo "$OUT" | grep -q "after busy=false killable=true" || fail "$wav: killable flag wrong after unload"
  WORDS="$(echo "$OUT" | grep -c "^word ")"
  [ "$WORDS" -ge 1 ] || fail "$wav: no words streamed"
  RTF="$(echo "$OUT" | sed -n 's/^result .* rtf=\([0-9.]*\)/\1/p')"
  [ -n "$RTF" ] || fail "$wav: no RTF reported"
  python3 -c "exit(0 if float('$RTF') < float('$RTF_LIMIT') else 1)" \
    || fail "$wav: rtf=$RTF over limit $RTF_LIMIT"
  echo "ok $wav words=$WORDS rtf=$RTF"
  N=$((N + 1))
done
[ "$N" -eq 5 ] || fail "expected 5 samples, ran $N"

# Unload proof: VRAM back to baseline, no backend processes lingering.
sleep 1
AFTER="$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1 | tr -d ' ')"
python3 -c "exit(0 if int('$AFTER') <= int('$BASELINE') + 50 else 1)" \
  || fail "VRAM not back to baseline: ${BASELINE}MiB -> ${AFTER}MiB"
LINGER="$(pgrep -f 'stt-manager/backend/transcribe.py' || true)"
[ -z "$LINGER" ] || fail "backend still resident after unload: $LINGER"

echo "GREEN: 5/5 samples streamed words, all RTF < $RTF_LIMIT, VRAM ${BASELINE}MiB -> ${AFTER}MiB, backends reaped"
