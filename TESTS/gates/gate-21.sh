#!/usr/bin/env bash
# Gate 21 — the daemon owns the model servers' lifecycle. GREEN only if:
#   1. with no launcher configured the daemon owns nothing (opt-in unchanged,
#      so a machine that hand-starts its servers behaves exactly as before),
#   2. a run spawns the formatter alongside the speech side (preloaded, so its
#      load overlaps speech instead of sitting after it) and keeps it warm when
#      the run ends, so the next run starts with the formatter still up,
#   3. whatever is left is killed once idle_timeout_s has passed with no run,
#      with no process left behind,
#   4. a port that already answers is left alone: neither spawned nor killed.
#
# Hermetic: stub launchers (`exec sleep`) stand in for the real scripts, so this
# runs with no GPU, no weights and no microphone. The real launchers are
# exercised by `vaani-key-service --servers-test` on a box that has them (see
# the build log).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate21.XXXXXX)"
HTTP_PID=0
cleanup() {
  [ "$HTTP_PID" -ne 0 ] && kill -KILL "$HTTP_PID" 2>/dev/null
  rm -rf "$TMP"
}
trap cleanup EXIT

BIN="$ROOT/target/debug/vaani-key-service"
if [ ! -x "$BIN" ]; then
  bad "missing $BIN (run: cargo build -p vaani-key-service)"
  echo "gate-21: $pass green, $fail red"
  exit 1
fi

# Stub launchers: record their own name and pid, then exec, which is exactly
# what the real serve-*.sh scripts do, so killing the child is enough.
SEQ="$TMP/seq"
PIDS="$TMP/pids"
for name in stt llm; do
  cat >"$TMP/$name.sh" <<EOF
#!/bin/sh
printf '$name\n' >> "$SEQ"
echo \$\$ >> "$PIDS"
exec sleep 300
EOF
  chmod +x "$TMP/$name.sh"
done

# 1. opt-in: nothing configured -> nothing owned. VAANI_ENV_FILE="" keeps the
#    installed env file out of the check, so it tests the opt-in itself.
out="$(env -u VAANI_STT_REFINE_SERVER -u VAANI_LLM_SERVER VAANI_ENV_FILE= "$BIN" --servers-test 2>&1)"
if grep -q "step=owned count=0" <<<"$out"; then
  ok "no launcher configured: daemon owns nothing"
else
  bad "expected 'step=owned count=0', got: $out"
fi

# 2/3. lifecycle on free ports.
out="$("$BIN" --servers-test "$TMP/stt.sh" "$TMP/llm.sh" 18083 18082 2>&1)"
grep -q "step=start name=stt spawned=true" <<<"$out" \
  && ok "speech server spawned" || bad "speech server not spawned: $out"
grep -q "step=start name=llm spawned=true" <<<"$out" \
  && ok "formatter preloaded alongside speech" || bad "formatter not preloaded: $out"
grep -q "step=keep name=llm running=true" <<<"$out" \
  && ok "formatter kept warm at the end of the run (idle window, not stopped)" \
  || bad "formatter not kept warm at the end of the run: $out"
keep_at="$(grep -n '^step=keep name=llm running=true' <<<"$out" | head -1 | cut -d: -f1)"
next_stt_at="$(grep -n '^step=start name=stt spawned=true' <<<"$out" | tail -1 | cut -d: -f1)"
if [ -n "$keep_at" ] && [ -n "$next_stt_at" ] && [ "$keep_at" -lt "$next_stt_at" ]; then
  ok "formatter is still warm when the next speech run starts"
else
  bad "keep/next-start order: keep='${keep_at:-none}' next stt start='${next_stt_at:-none}'"
fi
grep -q "servers ok killed_after_idle=true" <<<"$out" \
  && ok "leftover server judged due and killed after the idle window" \
  || bad "not killed after the idle window: $out"

seq_seen="$(tr '\n' ' ' <"$SEQ" 2>/dev/null | sed 's/ *$//')"
# Both preloads race their first shell line, so either may land first; what is
# ordered is the next run's speech start, after both.
read -r a b c <<<"$seq_seen"
if [ "$c" = "stt" ] && { { [ "$a" = "stt" ] && [ "$b" = "llm" ]; } || { [ "$a" = "llm" ] && [ "$b" = "stt" ]; }; }; then
  ok "launcher order: both preloaded at run start, then speech for the next run ('$seq_seen')"
else
  bad "launcher order was '$seq_seen', wanted both preloads then stt"
fi

left=0
while read -r p; do
  [ -n "$p" ] || continue
  kill -0 "$p" 2>/dev/null && left=$((left + 1))
done <"$PIDS"
[ "$left" -eq 0 ] \
  && ok "no launcher process left behind (pids recorded by the stubs)" \
  || bad "$left launcher process(es) survived the offload"

# 4. a port that already answers is left alone: not spawned and not killed.
python3 -m http.server 18084 --bind 127.0.0.1 >/dev/null 2>&1 &
HTTP_PID=$!
sleep 1
: >"$SEQ"
out="$("$BIN" --servers-test "$TMP/stt.sh" "$TMP/llm.sh" 18084 18085 2>&1)"
if grep -q "step=start name=stt spawned=false external=true" <<<"$out"; then
  ok "already-serving port: not spawned"
else
  bad "expected spawned=false external=true: $out"
fi
if grep -q '^stt$' "$SEQ"; then
  bad "the speech launcher ran for a port this daemon does not own"
else
  ok "already-serving port: the speech launcher never ran"
fi
if kill -0 "$HTTP_PID" 2>/dev/null; then
  ok "already-serving server still up (not ours to kill)"
else
  bad "killed a server this daemon does not own"
fi

echo "gate-21: $pass green, $fail red"
[ "$fail" -eq 0 ]
