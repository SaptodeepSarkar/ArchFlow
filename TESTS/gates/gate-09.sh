#!/usr/bin/env bash
# Gate 09 (key-lifecycle): STT unloads before the formatter loads
# (VRAM peaks serialized), busy helpers are never killed.
# GREEN only if the handoff runs end to end AND gate 03 still passes.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate09.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# 1. binary builds
if cargo build --release -p vaani-key-service >"$TMP/build.log" 2>&1; then
  ok "vaani-key-service builds"
else
  bad "vaani-key-service builds (see $TMP/build.log)"
  printf 'gate-09: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-09 RED"; exit 1
fi
BIN="$ROOT/target/release/vaani-key-service"

# 2. handoff runs end to end on a sample (raw transcript from fixture f0)
SAMPLE="$(python3 -c "import json; print(json.load(open('TESTS/fixtures/formatting.json'))[0]['raw'])")"
if "$BIN" --handoff-test "$SAMPLE" >"$TMP/handoff.log" 2>&1; then
  ok "handoff exits 0 on sample ($SAMPLE)"
else
  bad "handoff exits 0 (see $TMP/handoff.log)"; cat "$TMP/handoff.log"
fi

# 3. step order: stream -> unload -> load -> feed
ORDER="$(sed -n 's/^handoff ok .* order=//p' "$TMP/handoff.log")"
if [ "$ORDER" = "stt_stream,stt_unload,fmt_load,fmt_format,fmt_unload" ]; then
  ok "handoff order serialized ($ORDER)"
else
  bad "handoff order serialized (got '$ORDER')"
fi

# 4. VRAM sampled (numeric) at every step; never co-resident
STEPS="$(grep -c '^step=.* vram_mb=[0-9][0-9]* stt_loaded=.* fmt_loaded=' "$TMP/handoff.log" || true)"
if [ "$STEPS" -eq 5 ]; then
  ok "VRAM sampled at all 5 steps"
else
  bad "VRAM sampled at all 5 steps (got $STEPS)"
fi
if grep -q 'stt_loaded=true fmt_loaded=true' "$TMP/handoff.log"; then
  bad "no VRAM overlap (found co-resident step)"
else
  ok "no VRAM overlap (peaks serialized)"
fi
PEAK="$(sed -n 's/^handoff ok .* vram_peak_mb=\([0-9]*\).*/\1/p' "$TMP/handoff.log")"
[ -n "$PEAK" ] && ok "VRAM peak reported (${PEAK} MiB)" || bad "VRAM peak reported"

# 5. busy helpers never killed
if grep -q 'busy_kill_refused=true idle_offload_allowed=true' "$TMP/handoff.log"; then
  ok "busy kill refused, idle offload allowed"
else
  bad "busy kill refused, idle offload allowed"
fi

# 6. gate 03 still passes (hotkey-idle behavior unchanged)
if TESTS/gates/gate-03.sh >"$TMP/gate03.log" 2>&1; then
  ok "gate 03 still GREEN"
else
  bad "gate 03 still GREEN (see $TMP/gate03.log)"; tail -12 "$TMP/gate03.log"
fi

printf 'gate-09: %d passed, %d failed (vram peak %s MiB)\n' "$pass" "$fail" "${PEAK:-?}"
if [ "$fail" -eq 0 ]; then echo "gate-09 GREEN"; exit 0; else echo "gate-09 RED"; exit 1; fi
