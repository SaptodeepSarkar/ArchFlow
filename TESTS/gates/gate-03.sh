#!/usr/bin/env bash
# Phase 03 gate (hotkey-idle): resident key service grabs SUPER+H through the
# compositor, idles small, handles the trigger, shuts down cleanly.
# Exits 0 (GREEN) only if every check passes.
#
# NOTE: a live synthesized keypress (wtype) does NOT drive Hyprland binds on
# this machine (verified: even the user's own config-file SUPER+9 bind ignores
# wtype). The gate therefore fires the bind's exact registered dispatcher
# (`kill -USR1 <pid>` — byte-for-byte what the compositor runs on SUPER+H)
# instead of a fake keypress.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate03.XXXXXX)"
SRV=0
cleanup() {
  if [ "$SRV" -ne 0 ] && kill -0 "$SRV" 2>/dev/null; then
    kill -TERM "$SRV" 2>/dev/null
    sleep 1
    kill -KILL "$SRV" 2>/dev/null
    hyprctl eval "vaani_hotkey_${SRV}:remove()" >/dev/null 2>&1
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT

# 0. live compositor socket (Hyprland may have restarted; find newest live one)
if ! hyprctl binds >/dev/null 2>&1; then
  for d in $(ls -dt /run/user/$(id -u)/hypr/*/ 2>/dev/null); do
    if [ -S "${d}.socket.sock" ]; then
      export HYPRLAND_INSTANCE_SIGNATURE
      HYPRLAND_INSTANCE_SIGNATURE="$(basename "$d")"
      break
    fi
  done
fi
if ! hyprctl binds >/dev/null 2>&1; then
  bad "hyprctl reachable (no live Hyprland socket)"
  printf 'gate-03: %d passed, %d failed\n' "$pass" "$fail"
  echo "gate-03 RED"; exit 1
fi
ok "hyprctl reachable (instance $HYPRLAND_INSTANCE_SIGNATURE)"

hhandle() { # 1 if OUR Lua bind handle exists, else 0 (hyprctl binds -j
  # cannot see Lua-registered binds, so classic-bind counting is vacuous;
  # assert against the handle global instead).
  if hyprctl eval "assert(vaani_hotkey_${SRV} ~= nil)" >/dev/null 2>&1; then echo 1; else echo 0; fi
}

# 1. binary builds
if cargo build --release -p vaani-key-service >"$TMP/build.log" 2>&1; then
  ok "vaani-key-service builds"
else
  bad "vaani-key-service builds (see $TMP/build.log)"
fi
BIN="$ROOT/target/release/vaani-key-service"
[ -x "$BIN" ] || { bad "release binary present at $BIN"; printf 'gate-03: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-03 RED"; exit 1; }

# 2. service starts, parses config once, reaches idle
printf 'hotkey = SUPER+H\nui_words = 4\nidle_timeout_s = 120\n' >"$TMP/vaani.conf"
"$BIN" "$TMP/vaani.conf" >"$TMP/svc.log" 2>&1 &
SRV=$!
IDLE=0
for _ in $(seq 1 50); do
  grep -q 'state=idle' "$TMP/svc.log" 2>/dev/null && { IDLE=1; break; }
  kill -0 "$SRV" 2>/dev/null || break
  sleep 0.1
done
if [ "$IDLE" -eq 1 ]; then
  ok "service reaches idle (config parsed once)"
else
  bad "service reaches idle (see $TMP/svc.log)"
fi

# 3. hotkey binding registered via the compositor (own Lua handle present)
if [ "$(hhandle)" -eq 1 ]; then
  ok "SUPER+H Lua handle vaani_hotkey_${SRV} registered via hyprctl"
else
  bad "SUPER+H Lua handle registered (vaani_hotkey_${SRV} missing)"
fi

# 4. idle RSS under 20MB
RSS="$(awk '/VmRSS/ {print $2}' /proc/"$SRV"/status 2>/dev/null || echo 0)"
if [ "$RSS" -gt 0 ] && [ "$RSS" -lt 20480 ]; then
  ok "idle RSS ${RSS} kB under 20MB"
else
  bad "idle RSS under 20MB (got '${RSS}' kB)"
fi

# 5. hotkey dispatcher fires the service, which stays resident.
# The trigger now starts a live run (toggle): send a 2nd press to stop it.
# Stub wtype first on PATH so a non-silent mic can never type for real here.
mkdir -p "$TMP/shim"
printf '#!/usr/bin/env bash\necho "stub-fired $1" >>"$VAANI_WTYPE_LOG"\n' >"$TMP/shim/wtype"
chmod +x "$TMP/shim/wtype"
export PATH="$TMP/shim:$PATH" VAANI_WTYPE_LOG="$TMP/wtype.log"
: >"$VAANI_WTYPE_LOG"
kill -USR1 "$SRV" 2>/dev/null # exact command the bind's dispatcher runs
TRIG=0
for _ in $(seq 1 30); do
  grep -q 'state=triggered' "$TMP/svc.log" 2>/dev/null && { TRIG=1; break; }
  sleep 0.1
done
kill -USR1 "$SRV" 2>/dev/null # 2nd press: stop recording, run the pipeline
FIN=0
for _ in $(seq 1 120); do
  grep -q 'run finished' "$TMP/svc.log" 2>/dev/null && { FIN=1; break; }
  sleep 0.5
done
if [ "$TRIG" -eq 1 ] && [ "$FIN" -eq 1 ] && kill -0 "$SRV" 2>/dev/null; then
  ok "hotkey trigger logged, toggle run finished, service still resident"
else
  bad "hotkey trigger logged and resident (trig=$TRIG fin=$FIN; see $TMP/svc.log)"
fi

# 6. no helpers spawned (no children, no helper processes anywhere)
CHILDREN="$(ps --ppid "$SRV" --no-headers 2>/dev/null | wc -l)"
HELPERS="$(pgrep -f 'audio-helper|stt-manager|llm-formatter|typing-helper|quickshell.*pill' 2>/dev/null | wc -l)"
if [ "$CHILDREN" -eq 0 ] && [ "$HELPERS" -eq 0 ]; then
  ok "no helpers spawned (children=0, helpers=0)"
else
  bad "no helpers spawned (children=$CHILDREN helpers=$HELPERS)"
fi

# 7. clean shutdown on SIGTERM: exit 0, transition logged, bind removed
kill -TERM "$SRV" 2>/dev/null
wait "$SRV" 2>/dev/null
CODE=$?
SHUT=0
grep -q 'state=shutting down' "$TMP/svc.log" 2>/dev/null && SHUT=1
END_H=1
for _ in $(seq 1 50); do
  END_H="$(hhandle)"
  [ "$END_H" -eq 0 ] && break
  sleep 0.1
done
if [ "$CODE" -eq 0 ] && [ "$SHUT" -eq 1 ] && [ "$END_H" -eq 0 ]; then
  ok "SIGTERM: exit 0, shutdown logged, Lua handle removed"
else
  bad "SIGTERM shutdown (exit=$CODE logged=$SHUT handle-still-present=$END_H)"
fi
SRV=0 # already reaped; trap becomes a no-op for the kill

printf 'gate-03: %d passed, %d failed (idle RSS %s kB)\n' "$pass" "$fail" "$RSS"
if [ "$fail" -eq 0 ]; then echo "gate-03 GREEN"; exit 0; else echo "gate-03 RED"; exit 1; fi
