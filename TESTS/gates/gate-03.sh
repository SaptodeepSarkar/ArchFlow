#!/usr/bin/env bash
# Phase 03 gate (hotkey-idle): the resident key service publishes a pid file,
# idles small, runs a toggle cycle on signal, and shuts down cleanly.
# Exits 0 (GREEN) only if every check passes.
#
# Vaani never binds keys at runtime. hyprctl eval + :remove() on Hyprland
# 0.56.2 frees same-key binds by signature, so Lua handles dangle and the
# compositor SIGSEGVs (upstream bug). The bind is static in hyprland.lua and
# signals us via packaging/vaani-trigger; this gate therefore never calls
# `hyprctl eval`, and check 1 asserts the source never does either.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate03.XXXXXX)"
# NOTE: XDG_RUNTIME_DIR is left as-is on purpose: overriding it breaks
# PipeWire's socket lookup and the mic would deliver zero bytes.
PIDFILE="${XDG_RUNTIME_DIR:-$HOME/.cache}/vaani-key.pid"
ENVFILE="${PIDFILE%.pid}.env"
SRV=0
cleanup() {
  if [ "$SRV" -ne 0 ] && kill -0 "$SRV" 2>/dev/null; then
    kill -KILL "$SRV" 2>/dev/null
  fi
  rm -f "$PIDFILE" "$ENVFILE"
  rm -rf "$TMP"
}
trap cleanup EXIT

# 1. source never calls hyprctl (the crash vector must not exist at all)
if grep -rn "hyprctl" crates/key-service/src/*.rs 2>/dev/null | grep -qv '^\S*:[0-9]*://'; then
  bad "key-service source is free of hyprctl calls (comment-only mentions allowed)"
else
  ok "key-service source is free of hyprctl calls"
fi

# 2. binary builds
if cargo build --release -p vaani-key-service >"$TMP/build.log" 2>&1; then
  ok "vaani-key-service builds"
else
  bad "vaani-key-service builds (see $TMP/build.log)"
fi
BIN="$ROOT/target/release/vaani-key-service"
[ -x "$BIN" ] || { bad "release binary present at $BIN"; printf 'gate-03: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-03 RED"; exit 1; }

# 3. service starts, parses config once, publishes its pid
printf 'ui_words = 4\nidle_timeout_s = 120\n' >"$TMP/vaani.conf"
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
if [ -f "$PIDFILE" ] && [ "$(cat "$PIDFILE")" = "$SRV" ]; then
  ok "pid file published for the trigger script ($PIDFILE)"
else
  bad "pid file published (got '$(cat "$PIDFILE" 2>/dev/null)', want $SRV)"
fi

# 4. idle RSS under 20MB
RSS="$(awk '/VmRSS/ {print $2}' /proc/"$SRV"/status 2>/dev/null || echo 0)"
if [ "$RSS" -gt 0 ] && [ "$RSS" -lt 20480 ]; then
  ok "idle RSS ${RSS} kB under 20MB"
else
  bad "idle RSS under 20MB (got '${RSS}' kB)"
fi

# 5. toggle cycle through the real trigger script (stub wtype on PATH so a
# non-silent mic can never type for real here).
mkdir -p "$TMP/shim"
printf '#!/usr/bin/env bash\necho "stub-fired $1" >>"$VAANI_WTYPE_LOG"\n' >"$TMP/shim/wtype"
chmod +x "$TMP/shim/wtype"
export PATH="$TMP/shim:$PATH" VAANI_WTYPE_LOG="$TMP/wtype.log"
# The trigger is spawned by Hyprland, so whatever display it sees is the
# live socket; the service must adopt that instead of a stale systemd env.
export WAYLAND_DISPLAY="wayland-gate-test"
: >"$VAANI_WTYPE_LOG"
"$ROOT/packaging/vaani-trigger"   # press 1
TRIG=0
for _ in $(seq 1 30); do
  grep -q 'state=triggered' "$TMP/svc.log" 2>/dev/null && { TRIG=1; break; }
  sleep 0.1
done
if [ -f "$XDG_RUNTIME_DIR/vaani-key.env" ] \
    && grep -q '^WAYLAND_DISPLAY=wayland-gate-test$' "$XDG_RUNTIME_DIR/vaani-key.env"; then
  ok "trigger published the live wayland env"
else
  bad "trigger published the live wayland env (file: $(cat "$XDG_RUNTIME_DIR/vaani-key.env" 2>/dev/null | tr '\n' ' '))"
fi
if grep -q 'state=triggered .*display=wayland-gate-test' "$TMP/svc.log" 2>/dev/null; then
  ok "service adopted the trigger's wayland display"
else
  bad "service adopted the trigger's display (see $TMP/svc.log)"
fi
"$ROOT/packaging/vaani-trigger"   # press 2
FIN=0
for _ in $(seq 1 120); do
  grep -q 'run finished' "$TMP/svc.log" 2>/dev/null && { FIN=1; break; }
  sleep 0.5
done
if [ "$TRIG" -eq 1 ] && [ "$FIN" -eq 1 ] && kill -0 "$SRV" 2>/dev/null; then
  ok "trigger script drove a full toggle run, service still resident"
else
  bad "trigger script toggle run (trig=$TRIG fin=$FIN; see $TMP/svc.log)"
fi

# 6. clean shutdown on SIGTERM: exit 0, transition logged, pid file removed
kill -TERM "$SRV" 2>/dev/null
wait "$SRV" 2>/dev/null
CODE=$?
SHUT=0
grep -q 'state=shutting down' "$TMP/svc.log" 2>/dev/null && SHUT=1
GONE=1
for _ in $(seq 1 50); do
  [ -f "$PIDFILE" ] || { GONE=0; break; }
  sleep 0.1
done
if [ "$CODE" -eq 0 ] && [ "$SHUT" -eq 1 ] && [ "$GONE" -eq 0 ]; then
  ok "SIGTERM: exit 0, shutdown logged, pid file removed"
else
  bad "SIGTERM shutdown (exit=$CODE logged=$SHUT pidfile-still-present=$GONE)"
fi
SRV=0 # already reaped; trap becomes a no-op for the kill

# 7. A stale pid must not signal an unrelated process.
sleep 5 &
SPID=$!
echo "$SPID" >"$PIDFILE"
"$ROOT/packaging/vaani-trigger"
if kill -0 "$SPID" 2>/dev/null; then
  ok "stale pid was not signalled"
else
  bad "stale pid signalled an unrelated process"
fi
kill "$SPID" 2>/dev/null
rm -f "$PIDFILE" "$ENVFILE"

printf 'gate-03: %d passed, %d failed (idle RSS %s kB)\n' "$pass" "$fail" "$RSS"
if [ "$fail" -eq 0 ]; then echo "gate-03 GREEN"; exit 0; else echo "gate-03 RED"; exit 1; fi
