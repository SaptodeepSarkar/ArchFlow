#!/usr/bin/env bash
# Gate 09 (key-lifecycle): STT unloads before the formatter loads
# (VRAM peaks serialized), busy helpers are never killed.
# GREEN only if the handoff runs end to end, the daemon's real server lifecycle
# unloads one model before the other starts, AND gate 03 still passes.
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

# 6. real server lifecycle: --servers-test calls the same
# servers::start_stt / servers::handoff_to_llm that run_pipeline does. The stub
# launchers are the witnesses, not the daemon's own log: each start line carries
# a timestamp and whether the other launcher's pid was alive at that instant,
# and the speech stub records its stop when the daemon's SIGTERM arrives.
SEQ="$TMP/seq"
STT_PID="$TMP/stt.pid"
LLM_PID="$TMP/llm.pid"
cat >"$TMP/stt.sh" <<EOF
#!/bin/sh
trap 'kill \$child 2>/dev/null; printf "stop stt %s\n" "\$(date +%s%N)" >> "$SEQ"; exit 0' TERM
printf 'start stt %s llm_alive=%s\n' "\$(date +%s%N)" "\$( [ -f "$LLM_PID" ] && kill -0 "\$(cat "$LLM_PID")" 2>/dev/null && echo yes || echo no)" >> "$SEQ"
echo \$\$ > "$STT_PID"
sleep 300 & child=\$!
wait \$child
EOF
cat >"$TMP/llm.sh" <<EOF
#!/bin/sh
trap 'kill \$child 2>/dev/null; printf "stop llm %s\n" "\$(date +%s%N)" >> "$SEQ"; exit 0' TERM
printf 'start llm %s stt_alive=%s\n' "\$(date +%s%N)" "\$( [ -f "$STT_PID" ] && kill -0 "\$(cat "$STT_PID")" 2>/dev/null && echo yes || echo no)" >> "$SEQ"
echo \$\$ > "$LLM_PID"
sleep 300 & child=\$!
wait \$child
EOF
chmod +x "$TMP/stt.sh" "$TMP/llm.sh"

if "$BIN" --servers-test "$TMP/stt.sh" "$TMP/llm.sh" 18183 18182 >"$TMP/servers.log" 2>&1; then
  ok "server lifecycle: speech start -> handoff -> formatter -> next run -> idle sweep"
else
  bad "server lifecycle: speech start -> handoff -> formatter -> next run -> idle sweep (see $TMP/servers.log)"
  cat "$TMP/servers.log"
fi

LLM_START="$(grep '^start llm ' "$SEQ" 2>/dev/null | head -1)"
if printf '%s' "$LLM_START" | grep -q 'stt_alive=no$'; then
  ok "formatter launcher saw the speech launcher already dead (stt_alive=no)"
else
  bad "formatter launcher saw the speech launcher already dead (got '${LLM_START:-nothing}')"
fi

STT_STOP_NS="$(awk '$1=="stop" && $2=="stt" {print $3}' "$SEQ" 2>/dev/null | head -1)"
LLM_START_NS="$(awk '$1=="start" && $2=="llm" {print $3}' "$SEQ" 2>/dev/null | head -1)"
if [ -n "$STT_STOP_NS" ] && [ -n "$LLM_START_NS" ] && [ "$STT_STOP_NS" -lt "$LLM_START_NS" ]; then
  ok "speech stop timestamp precedes the formatter start"
else
  bad "speech stop timestamp precedes the formatter start (stop='${STT_STOP_NS:-none}' start='${LLM_START_NS:-none}')"
fi

LAST_STT_START="$(grep '^start stt ' "$SEQ" 2>/dev/null | tail -1)"
if printf '%s' "$LAST_STT_START" | grep -q 'llm_alive=no$'; then
  ok "next run's speech launcher saw the formatter already dead (llm_alive=no)"
else
  bad "next run's speech launcher saw the formatter already dead (got '${LAST_STT_START:-nothing}')"
fi

# 7. gate 03 still passes (hotkey-idle behavior unchanged)
if TESTS/gates/gate-03.sh >"$TMP/gate03.log" 2>&1; then
  ok "gate 03 still GREEN"
else
  bad "gate 03 still GREEN (see $TMP/gate03.log)"; tail -12 "$TMP/gate03.log"
fi

printf 'gate-09: %d passed, %d failed (vram peak %s MiB)\n' "$pass" "$fail" "${PEAK:-?}"
if [ "$fail" -eq 0 ]; then echo "gate-09 GREEN"; exit 0; else echo "gate-09 RED"; exit 1; fi
