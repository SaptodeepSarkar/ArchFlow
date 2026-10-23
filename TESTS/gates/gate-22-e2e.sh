#!/usr/bin/env bash
# Gate 22 — hermetic end-to-end. GREEN only if the real daemon binary:
#   1. boots with stub backends, publishes its pid file + control socket,
#      reports IDLE and exits cleanly on SIGTERM,
#   2. is driven by the real packaging/vaani-trigger script and moves to
#      STARTING (this proves the static-bind -> pid file -> SIGUSR1 path; it is
#      NOT a physical SUPER+H press, which needs Hyprland),
#   3. runs a fixture wav through --pipeline-test with a stub STT backend and
#      lands the expected text in the typing backend (stub wtype first on PATH),
#   4. runs the full record -> decode -> format -> type loop from a trigger and
#      reports READY with byte-exact keystrokes,
#   5. handles every failure path (no STT python, missing model, unreadable wav,
#      dead LLM endpoint, dead control socket) without hanging and without
#      leaving a helper behind, ending in ERROR where the daemon has that
#      state and in the documented fallback where it does not (dead LLM ->
#      rule engine), with the missing-model reason naming the configured path,
#   6. writes no *.wav* under /tmp,
#   7. cancels a run while it is TRANSCRIBING (the overlay's Cancel button in
#      that state): a `stop` op on the control socket ends the run in CANCELLED
#      and types nothing.
#
# Honest scope: a GitHub runner has no microphone, no Hyprland, no GPU and no
# model server. This gate stubs pw-record, the STT backend and wtype, so it
# proves the daemon's plumbing and its failure handling -- not audio capture,
# not speech accuracy and not the keybinding itself. Those stay on the machine.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

BIN="$ROOT/target/debug/vaani-key-service"
if [ ! -x "$BIN" ]; then
  bad "daemon binary missing (build first: cargo build --workspace)"
  printf 'gate-22: %d passed, %d failed\n' "$pass" "$fail"
  echo "gate-22 RED"
  exit 1
fi

TMP="$(mktemp -d /tmp/vaani-gate22.XXXXXX)"
SRV=0; CLIENT=0
cleanup() {
  [ "$CLIENT" -ne 0 ] && kill -KILL "$CLIENT" 2>/dev/null
  [ "$SRV" -ne 0 ] && kill -KILL "$SRV" 2>/dev/null
  rm -rf "$TMP"
}
trap cleanup EXIT

# Private runtime dir: pid file, control socket and the trigger all resolve
# through XDG_RUNTIME_DIR, so the gate never touches the user's live daemon.
mkdir -p "$TMP/run" "$TMP/model" "$TMP/shim"
chmod 700 "$TMP/run"
export XDG_RUNTIME_DIR="$TMP/run"
export PATH="$TMP/shim:$PATH"
export VAANI_STT_PYTHON="$TMP/stub-stt"
export VAANI_GATE22_PIDS="$TMP/pids"
export VAANI_GATE22_TYPED="$TMP/typed.txt"
export VAANI_GATE22_WTYPE_LOG="$TMP/wtype.log"
# The optional second pass and owned model servers must not run here: a stray
# refine backend would add a network deadline to every case.
unset VAANI_STT_MODEL VAANI_STT_BACKEND VAANI_STT_REFINE_BACKEND \
      VAANI_STT_REFINE_ENDPOINT VAANI_STT_REFINE_SERVER VAANI_LLM_SERVER
export VAANI_LLM_ENDPOINT="http://127.0.0.1:1"

PIDFILE="$TMP/run/vaani-key.pid"
SOCK="$TMP/run/vaani/control.sock"

# --- stubs (exec edges only: mic, speech model, keystrokes) ---
# pw-record stub: paced 100 ms chunks of silence, records its pid. Python (not
# a shell loop) so killing it never leaves a `sleep` child behind.
cat >"$TMP/shim/pw-record" <<'EOF'
#!/usr/bin/env python3
import os, time
with open(os.environ["VAANI_GATE22_PIDS"], "a") as f:
    f.write(f"{os.getpid()}\n")
chunk = b"\0" * 3200
while True:
    os.write(1, chunk)
    time.sleep(0.1)
EOF

# wtype stub: records the exact argv it was handed.
cat >"$TMP/shim/wtype" <<'EOF'
#!/usr/bin/env bash
[ "$#" -eq 1 ] || { echo "stub wtype: expected 1 arg, got $#" >&2; exit 1; }
printf '%s' "$1" >"$VAANI_GATE22_TYPED"
printf 'wtype-fired bytes=%s\n' "${#1}" >>"$VAANI_GATE22_WTYPE_LOG"
EOF
chmod +x "$TMP/shim/pw-record" "$TMP/shim/wtype"

# No real overlay in a gate: quickshell exits at once (the daemon logs the
# spawn failure on a runner, which is also fine, but this keeps it quiet).
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/shim/quickshell"
chmod +x "$TMP/shim/quickshell"

# STT stub: answers `-c "import vosk"` (the interpreter probe), then emits the
# fixed word "hello" for both backend modes. Batch (--wav) exits after DONE;
# stream (--stream) drains mic PCM until the daemon closes stdin, then DONE.
# VAANI_GATE22_STT_PAUSE (cancel case only) delays that DONE so the daemon
# stays in TRANSCRIBING long enough for the gate to send a stop.
cat >"$TMP/stub-stt" <<'EOF'
#!/bin/sh
[ "$1" = "-c" ] && exit 0
echo $$ >>"$VAANI_GATE22_PIDS"
stream=0
for a in "$@"; do [ "$a" = "--stream" ] && stream=1; done
if [ "$stream" = 1 ]; then
  printf 'W 0.00 hello\n'
  cat >/dev/null
  [ -n "${VAANI_GATE22_STT_PAUSE:-}" ] && sleep "$VAANI_GATE22_STT_PAUSE"
else
  printf 'W 0.00 hello\n'
fi
printf 'DONE audio=1.00 infer=0.05 words=1\n'
EOF
chmod +x "$TMP/stub-stt"

cat >"$TMP/ok.conf" <<EOF
ui_words = 4
stt_model = $TMP/model
stt_fallback_model = base.en
idle_timeout_s = 120
end_of_speech_ms = 600
EOF
cat >"$TMP/bad-model.conf" <<EOF
ui_words = 4
stt_model = /nonexistent/vaani-model
stt_fallback_model = base.en
idle_timeout_s = 120
end_of_speech_ms = 600
EOF

# Control-socket client: appends one STATE=<name> line (and the state detail as
# MSG=<text>) per state event so the gate can wait on transitions without
# reading the daemon's log format. With two more args it sends one op line as
# soon as the named state appears -- the overlay's Cancel button.
cat >"$TMP/client.py" <<'EOF'
import json, socket, sys, time

path, out, seconds = sys.argv[1], sys.argv[2], float(sys.argv[3])
send_on = sys.argv[4] if len(sys.argv) > 4 else ""
send_line = sys.argv[5] if len(sys.argv) > 5 else ""
deadline = time.time() + seconds
# A stale socket file can exist for a moment before the daemon rebinds it.
while True:
    s = socket.socket(socket.AF_UNIX)
    try:
        s.connect(path)
        break
    except (ConnectionRefusedError, FileNotFoundError):
        s.close()
        if time.time() > deadline:
            raise SystemExit(f"control socket never accepted a connection: {path}")
        time.sleep(0.05)
s.settimeout(0.2)
buf = b""
with open(out, "a") as f:
    while time.time() < deadline:
        try:
            chunk = s.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("state"):
                f.write("STATE=" + msg["state"] + "\n")
                f.write("MSG=" + msg.get("message", "") + "\n")
                f.flush()
                if send_on and msg["state"] == send_on:
                    s.sendall(send_line.encode() + b"\n")
                    send_on = ""
EOF

wait_state() { # $1=state $2=ticks (50ms each)
  local want="$1" ticks="${2:-100}" i
  for i in $(seq 1 "$ticks"); do
    grep -qx "STATE=$want" "$TMP/states" && return 0
    sleep 0.05
  done
  return 1
}

wait_file() { # $1=path $2=ticks
  local i
  for i in $(seq 1 "${2:-100}"); do [ -e "$1" ] && return 0; sleep 0.05; done
  return 1
}

# Start the daemon and attach the state client; the pid lands in SRV.
# $3/$4: state to wait for and the exact op line to send when it appears.
start_daemon() { # $1=conf $2=log [$3=state $4=op line]
  : >"$TMP/states"
  : >"$VAANI_GATE22_PIDS"
  "$BIN" "$1" >"$2" 2>&1 &
  SRV=$!
  if ! wait_file "$SOCK" 100; then
    bad "daemon opened its control socket (see $2)"
    return 1
  fi
  python3 "$TMP/client.py" "$SOCK" "$TMP/states" 20 "${3:-}" "${4:-}" &
  CLIENT=$!
  # Out of the job table: killing it below must not print "Killed" noise.
  disown "$CLIENT" 2>/dev/null || true
  return 0
}

stop_daemon() { # SIGTERM, up to 10s, then SIGKILL; exit code in RC
  kill -TERM "$SRV" 2>/dev/null
  local i
  for i in $(seq 1 100); do
    kill -0 "$SRV" 2>/dev/null || break
    sleep 0.1
  done
  # A daemon that ignores SIGTERM must fail this case in seconds, not sit on
  # the CI job's timeout.
  if kill -0 "$SRV" 2>/dev/null; then
    bad "shutdown: daemon ignored SIGTERM for 10s, killed with SIGKILL"
    kill -KILL "$SRV" 2>/dev/null
  fi
  wait "$SRV" 2>/dev/null
  RC=$?
  SRV=0
  [ "$CLIENT" -ne 0 ] && kill -KILL "$CLIENT" 2>/dev/null
  CLIENT=0
}

no_helpers_left() { # $1=label -> fail if a stub pid is still alive
  local p left=0
  while read -r p; do
    [ -n "$p" ] || continue
    kill -0 "$p" 2>/dev/null && left=$((left + 1))
  done <"$VAANI_GATE22_PIDS"
  if [ "$left" -eq 0 ]; then
    ok "$1: no resident helper process"
  else
    bad "$1: $left helper process(es) survived"
  fi
}

# ---------------------------------------------------------------- 1 + 2 + 4
# shortcut: the disk audit scans /tmp to depth 2; a writer nesting deeper
# would slip through. Upgrade if a component starts making its own temp dirs.
WAV_BEFORE="$(find /tmp -maxdepth 2 -name '*.wav*' 2>/dev/null | sort)"

start_daemon "$TMP/ok.conf" "$TMP/e2e.log" || true
if [ -f "$PIDFILE" ] && [ "$(cat "$PIDFILE")" = "$SRV" ]; then
  ok "startup: pid file published for the trigger script"
else
  bad "startup: pid file published (got '$(cat "$PIDFILE" 2>/dev/null)', want $SRV)"
fi
[ -S "$SOCK" ] && ok "startup: control socket created" || bad "startup: control socket created"
wait_state IDLE 100 && ok "startup: snapshot reports IDLE" || bad "startup: snapshot reports IDLE"

# The real trigger script, exactly what the static Hyprland bind runs.
"$ROOT/packaging/vaani-trigger"
if wait_state STARTING 100; then
  ok "trigger: vaani-trigger moved the daemon to STARTING (static-bind path, not a physical keypress)"
else
  bad "trigger: daemon reached STARTING (states: $(tr '\n' ' ' <"$TMP/states"))"
fi
grep -q 'state=triggered .*static bind fired' "$TMP/e2e.log" 2>/dev/null \
  && ok "trigger: daemon logged the static bind firing" \
  || bad "trigger: daemon logged the static bind firing"

if wait_state READY 200; then
  ok "e2e: full loop reached READY"
else
  bad "e2e: full loop reached READY (states: $(tr '\n' ' ' <"$TMP/states"), log: $(tail -3 "$TMP/e2e.log" | tr '\n' ' '))"
fi
for st in STARTING RECORDING TRANSCRIBING CLEANING INSERTING READY; do
  grep -qx "STATE=$st" "$TMP/states" && ok "e2e: state $st published" || bad "e2e: state $st published"
done
if [ "$(cat "$VAANI_GATE22_TYPED" 2>/dev/null)" = "Hello." ]; then
  ok "e2e: exact keystrokes typed (stub wtype got 'Hello.')"
else
  bad "e2e: exact keystrokes typed (got '$(cat "$VAANI_GATE22_TYPED" 2>/dev/null)')"
fi
[ "$(wc -l <"$VAANI_GATE22_WTYPE_LOG" 2>/dev/null || echo 0)" -eq 1 ] \
  && ok "e2e: wtype fired exactly once (real wtype never ran)" \
  || bad "e2e: wtype fired exactly once"

stop_daemon
[ "$RC" -eq 0 ] && ok "shutdown: SIGTERM exits 0" || bad "shutdown: SIGTERM exits 0 (got $RC)"
[ -f "$PIDFILE" ] && bad "shutdown: pid file removed" || ok "shutdown: pid file removed"
no_helpers_left "e2e run"

# ---------------------------------------------------------------------- 7
# Cancel while the daemon is TRANSCRIBING (the overlay enables Cancel in that
# state): the stop ends the run with CANCELLED and types nothing. The stub
# backend holds its DONE so the state stays observable for the gate.
: >"$VAANI_GATE22_WTYPE_LOG"
rm -f "$VAANI_GATE22_TYPED"
export VAANI_GATE22_STT_PAUSE=3
start_daemon "$TMP/ok.conf" "$TMP/cancel.log" TRANSCRIBING \
  '{"protocol_version":1,"request_id":"gate22-stop","session_id":null,"kind":{"op":"stop"}}' || true
"$ROOT/packaging/vaani-trigger"
wait_state TRANSCRIBING 100 && ok "cancel: daemon reached TRANSCRIBING" \
  || bad "cancel: daemon reached TRANSCRIBING (states: $(tr '\n' ' ' <"$TMP/states"))"
# The run must end by itself; read the terminal state once it lands.
last=""
for i in $(seq 1 200); do
  last="$(grep '^STATE=' "$TMP/states" | tail -1)"
  case "$last" in STATE=CANCELLED|STATE=IDLE|STATE=ERROR) break ;; esac
  sleep 0.05
done
[ "$last" = "STATE=CANCELLED" ] \
  && ok "cancel: stop during transcription ends in CANCELLED" \
  || bad "cancel: stop during transcription ends in CANCELLED (last: ${last:-none}, states: $(tr '\n' ' ' <"$TMP/states"))"
[ ! -s "$VAANI_GATE22_WTYPE_LOG" ] && [ ! -e "$VAANI_GATE22_TYPED" ] \
  && ok "cancel: nothing was typed" \
  || bad "cancel: nothing was typed (wtype log: $(cat "$VAANI_GATE22_WTYPE_LOG" 2>/dev/null))"
unset VAANI_GATE22_STT_PAUSE
stop_daemon
no_helpers_left "cancel during transcription"

# ---------------------------------------------------------------------- 3
# The documented test entry point, on a fixture wav, with the stub backend.
: >"$VAANI_GATE22_WTYPE_LOG"
rm -f "$VAANI_GATE22_TYPED"
OUT="$(timeout 15 "$BIN" --pipeline-test TESTS/fixtures/audio/s1-hello.wav "$TMP/ok.conf" 2>"$TMP/pipeline.err")"
RC=$?
if [ "$RC" -eq 0 ] && grep -qx 'PIPELINE-OK typed=Hello.' <<<"$OUT"; then
  ok "transcription: --pipeline-test reports typed=Hello."
else
  bad "transcription: --pipeline-test (rc=$RC out='$OUT' err='$(tail -1 "$TMP/pipeline.err")')"
fi
[ "$(cat "$VAANI_GATE22_TYPED" 2>/dev/null)" = "Hello." ] \
  && ok "typing: expected text reached the typing backend" \
  || bad "typing: expected text reached the typing backend (got '$(cat "$VAANI_GATE22_TYPED" 2>/dev/null)')"
no_helpers_left "pipeline-test"

# ---------------------------------------------------------------------- 5
# (a) no STT python: an explicitly configured interpreter that cannot import
# vosk is final -- it must not silently fall back to another one.
STUB_PY="$VAANI_STT_PYTHON"
export VAANI_STT_PYTHON=/nonexistent/vaani-python
start_daemon "$TMP/ok.conf" "$TMP/no-python.log" || true
export VAANI_STT_PYTHON="$STUB_PY"
"$ROOT/packaging/vaani-trigger"
wait_state ERROR 100 && ok "error: no STT python ends in ERROR" \
  || bad "error: no STT python ends in ERROR (states: $(tr '\n' ' ' <"$TMP/states"))"
stop_daemon
[ "$RC" -eq 0 ] && ok "error: no STT python does not hang or crash the daemon" \
  || bad "error: no STT python daemon exit (got $RC)"
no_helpers_left "no STT python"

# (b) missing model: a configured absolute path that does not exist is an
# error, never a silent default -- and the reason names the path the config
# asked for, so a dropped detail fails here.
start_daemon "$TMP/bad-model.conf" "$TMP/no-model.log" || true
"$ROOT/packaging/vaani-trigger"
wait_state ERROR 100 && ok "error: missing model path ends in ERROR" \
  || bad "error: missing model path ends in ERROR (states: $(tr '\n' ' ' <"$TMP/states"))"
grep -qi 'stt model unusable' "$TMP/no-model.log" "$TMP/states" 2>/dev/null \
  && ok "error: missing model is reported with its reason, not silently replaced" \
  || bad "error: missing model is reported with its reason"
grep -qi 'stt model unusable.*/nonexistent/vaani-model' "$TMP/no-model.log" "$TMP/states" 2>/dev/null \
  && ok "error: the reason names the configured path" \
  || bad "error: the reason names the configured path"
stop_daemon
[ "$RC" -eq 0 ] && ok "error: missing model does not hang or crash the daemon" \
  || bad "error: missing model daemon exit (got $RC)"
no_helpers_left "missing model"

# (c) unreadable wav: the batch entry point fails fast and non-zero.
START=$(date +%s)
VAANI_STT_MODEL="$TMP/model" timeout 10 "$BIN" --stream-test /nonexistent/vaani.wav \
  >"$TMP/bad-wav.log" 2>&1
RC=$?
TOOK=$(( $(date +%s) - START ))
[ "$RC" -ne 0 ] && grep -q '^STREAM-FAIL' "$TMP/bad-wav.log" \
  && ok "error: unreadable wav fails fast (rc=$RC, ${TOOK}s)" \
  || bad "error: unreadable wav (rc=$RC: $(tail -1 "$TMP/bad-wav.log"))"
[ "$RC" -ne 124 ] && ok "error: unreadable wav does not hang" || bad "error: unreadable wav hung"
no_helpers_left "unreadable wav"

# (d) dead LLM endpoint: the documented degrade is the rule engine, not an
# ERROR -- a missing formatter costs accuracy, never the utterance. Assert the
# fallback instead of pretending the daemon should fail.
timeout 10 "$BIN" --format-test "umm hello" "$TMP/ok.conf" >"$TMP/dead-llm.log" 2>&1
RC=$?
if [ "$RC" -eq 0 ] && grep -q '^FORMAT-TEST backend=rules text=Hello\.$' "$TMP/dead-llm.log"; then
  ok "error: dead LLM endpoint degrades to the rule engine (no hang)"
else
  bad "error: dead LLM endpoint (rc=$RC: $(tail -1 "$TMP/dead-llm.log"))"
fi
no_helpers_left "dead LLM endpoint"

# (e) dead control socket: a stale socket file must be replaced, while a live
# daemon's socket must not be stolen (the second daemon exits non-zero).
rm -f "$SOCK"
python3 - "$SOCK" <<'EOF'
import socket, sys
s = socket.socket(socket.AF_UNIX)
s.bind(sys.argv[1])
EOF
[ -S "$SOCK" ] || bad "error: stale control socket fixture created"
start_daemon "$TMP/ok.conf" "$TMP/stale-sock.log" || true
grep -q 'state=idle' "$TMP/stale-sock.log" 2>/dev/null \
  && ok "error: stale control socket replaced, daemon boots" \
  || bad "error: stale control socket replaced (see $TMP/stale-sock.log)"
timeout 10 "$BIN" "$TMP/ok.conf" >"$TMP/live-sock.log" 2>&1
RC=$?
[ "$RC" -ne 0 ] && [ "$RC" -ne 124 ] \
  && ok "error: live control socket refused, second daemon exits non-zero (rc=$RC)" \
  || bad "error: live control socket refused (rc=$RC)"
grep -q 'control socket unavailable' "$TMP/live-sock.log" 2>/dev/null \
  && ok "error: live control socket failure is reported" \
  || bad "error: live control socket failure is reported"
stop_daemon
no_helpers_left "control socket"

# ---------------------------------------------------------------------- 6
WAV_AFTER="$(find /tmp -maxdepth 2 -name '*.wav*' 2>/dev/null | sort)"
NEW_WAVS="$(comm -13 <(printf '%s\n' "$WAV_BEFORE") <(printf '%s\n' "$WAV_AFTER") | grep -v '^$' || true)"
if [ -z "$NEW_WAVS" ]; then
  ok "no disk: no new *.wav* under /tmp after the run"
else
  bad "no disk: new wav files appeared: $(tr '\n' ' ' <<<"$NEW_WAVS")"
fi

printf 'gate-22: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-22 GREEN"; exit 0; else echo "gate-22 RED"; exit 1; fi
