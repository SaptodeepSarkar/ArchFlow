#!/usr/bin/env bash
# Gate 09 (key-lifecycle): the formatter preloads at run start, speech is
# unloaded before formatting runs, busy helpers are never killed.
# GREEN only if the handoff runs end to end, the daemon's real server lifecycle
# preloads the formatter alongside speech, AND gate 03 still passes.
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

# 3. step order: preload -> stream -> unload stt -> format -> idle offload
ORDER="$(sed -n 's/^handoff ok .* order=//p' "$TMP/handoff.log")"
if [ "$ORDER" = "fmt_preload,stt_stream,stt_unload,fmt_format,fmt_idle" ]; then
  ok "handoff order: preload, stream, unload speech, format ($ORDER)"
else
  bad "handoff order (got '$ORDER')"
fi

# 4. VRAM sampled (numeric) at every step; the formatter is resident before
# speech and speech is gone before formatting runs.
STEPS="$(grep -c '^step=.* vram_mb=[0-9][0-9]* stt_loaded=.* fmt_loaded=' "$TMP/handoff.log" || true)"
if [ "$STEPS" -eq 5 ]; then
  ok "VRAM sampled at all 5 steps"
else
  bad "VRAM sampled at all 5 steps (got $STEPS)"
fi
if grep -q '^step=fmt_preload .* stt_loaded=false fmt_loaded=true' "$TMP/handoff.log" \
  && grep -q '^step=stt_stream .* stt_loaded=true fmt_loaded=true' "$TMP/handoff.log" \
  && grep -q '^step=fmt_format .* stt_loaded=false fmt_loaded=true' "$TMP/handoff.log"; then
  ok "formatter preloaded before speech; speech gone before formatting"
else
  bad "formatter preloaded before speech; speech gone before formatting"
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
if printf '%s' "$LLM_START" | grep -q 'stt_alive=yes$'; then
  ok "formatter launcher ran while the speech server was still up (preload)"
else
  bad "formatter launcher ran while the speech server was still up (got '${LLM_START:-nothing}')"
fi

STT_STOP_NS="$(awk '$1=="stop" && $2=="stt" {print $3}' "$SEQ" 2>/dev/null | head -1)"
LLM_START_NS="$(awk '$1=="start" && $2=="llm" {print $3}' "$SEQ" 2>/dev/null | head -1)"
if [ -n "$STT_STOP_NS" ] && [ -n "$LLM_START_NS" ] && [ "$LLM_START_NS" -lt "$STT_STOP_NS" ]; then
  ok "formatter starts before the speech server is stopped (preloaded, not after)"
else
  bad "formatter starts before the speech server is stopped (start='${LLM_START_NS:-none}' stop='${STT_STOP_NS:-none}')"
fi

LAST_STT_START="$(grep '^start stt ' "$SEQ" 2>/dev/null | tail -1)"
if printf '%s' "$LAST_STT_START" | grep -q 'llm_alive=yes$'; then
  ok "next run's speech launcher saw the formatter still warm (llm_alive=yes)"
else
  bad "next run's speech launcher saw the formatter still warm (got '${LAST_STT_START:-nothing}')"
fi

# 7. gate 03 still passes (hotkey-idle behavior unchanged)
if TESTS/gates/gate-03.sh >"$TMP/gate03.log" 2>&1; then
  ok "gate 03 still GREEN"
else
  bad "gate 03 still GREEN (see $TMP/gate03.log)"; tail -12 "$TMP/gate03.log"
fi

printf 'gate-09: %d passed, %d failed (vram peak %s MiB)\n' "$pass" "$fail" "${PEAK:-?}"
if [ "$fail" -eq 0 ]; then echo "gate-09 GREEN"; exit 0; else echo "gate-09 RED"; exit 1; fi
