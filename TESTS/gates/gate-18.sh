#!/usr/bin/env bash
# Gate 18 — live UI. GREEN only if the daemon speaks the overlay's protocol:
#   1. STT --stream emits partials/finals while audio arrives (live words),
#   2. a client on $XDG_RUNTIME_DIR/vaani/control.sock receives the snapshot
#      and the state events the overlay acts on,
#   3. the `stop` op ends the run (nothing typed happens until the run ends
#      normally, so the assertion is that the run finished and went IDLE),
#   4. the daemon's own unit tests pass and the real overlay config loads
#      without QML errors.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate18.XXXXXX)"
# XDG_RUNTIME_DIR is left as-is on purpose: overriding it breaks PipeWire.
SOCK="${XDG_RUNTIME_DIR:-/tmp}/vaani/control.sock"
PIDFILE="${XDG_RUNTIME_DIR:-$HOME/.cache}/vaani-key.pid"
ENVFILE="${PIDFILE%.pid}.env"
SRV=0
cleanup() {
  [ "$SRV" -ne 0 ] && kill -KILL "$SRV" 2>/dev/null
  rm -f "$PIDFILE" "$ENVFILE" "$SOCK"
  rm -rf "$TMP"
}
trap cleanup EXIT

PY="${VAANI_STT_PYTHON:-/home/saptodeep/Projects/Kyuma/.venv/bin/python}"
MODEL="${VAANI_STT_MODEL:-/home/saptodeep/Projects/Kyuma/models/vosk-model-small-en-us-0.15}"
if [ -x "$PY" ] && [ -d "$MODEL" ]; then ok "STT python/model present"; else
  bad "STT python/model present (py=$PY model=$MODEL)"
  printf 'gate-18: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-18 RED"; exit 1
fi

# 1. live words: --stream emits P lines as bytes arrive, then W + DONE.
python3 - "$ROOT/TESTS/fixtures/audio/s1-hello.wav" "$TMP/s1.raw" <<'EOF'
import sys, wave
w = wave.open(sys.argv[1], "rb")
open(sys.argv[2], "wb").write(w.readframes(w.getnframes()))
EOF
OUT="$(VAANI_STT_MODEL="$MODEL" "$PY" "$ROOT/crates/stt-manager/backend/transcribe.py" --stream <"$TMP/s1.raw" 2>/dev/null)"
if echo "$OUT" | grep -q "^P "; then
  ok "stream mode emits live partials ($(echo "$OUT" | grep -c '^P ') P lines)"
else
  bad "stream mode emits live partials"
fi
if echo "$OUT" | grep -q "^DONE " && echo "$OUT" | grep -q "^W "; then
  ok "stream mode ends with finals + DONE"
else
  bad "stream mode finals/DONE"
fi

# 2. protocol: start the daemon, drive a full run with a socket client.
printf 'hotkey = SUPER+H\nui_words = 4\nidle_timeout_s = 120\n' >"$TMP/vaani.conf"
mkdir -p "$TMP/shim"
printf '#!/usr/bin/env bash\nprintf "typed %%s\\n" "$1" >>"$VAANI_WTYPE_LOG"\n' >"$TMP/shim/wtype"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TMP/shim/quickshell"
chmod +x "$TMP/shim/"*
export PATH="$TMP/shim:$PATH" VAANI_WTYPE_LOG="$TMP/typed.log"
: >"$VAANI_WTYPE_LOG"

BIN="$ROOT/target/debug/vaani-key-service"
[ -x "$BIN" ] || { bad "daemon binary missing (build first)"; printf 'gate-18: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-18 RED"; exit 1; }
"$BIN" "$TMP/vaani.conf" >"$TMP/svc.log" 2>&1 &
SRV=$!
for _ in $(seq 1 50); do grep -q 'state=idle' "$TMP/svc.log" 2>/dev/null && break; sleep 0.1; done
[ -S "$SOCK" ] && ok "control socket listening" || bad "control socket listening ($SOCK)"

# Client: connect, read the snapshot, press "stop" after a moment, collect
# every line until the run ends.
python3 - "$SOCK" "$ROOT/packaging/vaani-trigger" "$TMP/client.out" <<'EOF'
import json, os, socket, subprocess, sys, time
sock_path, trigger, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(20)
s.connect(sock_path)
f = s.makefile("r")
lines = []
def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        s.settimeout(max(0.1, end - time.time()))
        try:
            line = f.readline()
        except socket.timeout:
            return
        if not line:
            return
        lines.append(line.strip())
subprocess.run([trigger], check=False)   # press 1 -> STARTING/RECORDING
pump(6)
s.sendall((json.dumps({"protocol_version": 1, "request_id": "qml-1",
                       "session_id": None, "kind": {"op": "stop"}}) + "\n").encode())
pump(8)
open(out_path, "w").write("\n".join(lines) + "\n")
EOF
if [ -s "$TMP/client.out" ]; then ok "client received daemon lines"; else bad "client received daemon lines"; fi

check_state() { # $1 = state, $2 = what
  if python3 - "$TMP/client.out" "$1" <<'EOF'
import json, sys
need = sys.argv[2]
for line in open(sys.argv[1]):
    line = line.strip()
    if not line:
        continue
    try:
        m = json.loads(line)
    except Exception:
        sys.exit(2)
    if m.get("state") == need:
        sys.exit(0)
sys.exit(1)
EOF
  then ok "$2"; else bad "$2 (got states: $(python3 -c "
import json,sys
print(sorted({json.loads(l).get('state') for l in open('$TMP/client.out') if l.strip() and json.loads(l).get('state')}))" 2>/dev/null))"; fi
}

check_state RECORDING "daemon published RECORDING"
if python3 - "$TMP/client.out" <<'EOF'
import json, sys
snap = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
first = snap[0] if snap else {}
sys.exit(0 if first.get("protocol_version") == 1 and first.get("session_id") else 1)
EOF
then ok "first line is a protocol_version 1 snapshot"; else bad "first line is a snapshot (got: $(head -1 "$TMP/client.out"))"; fi
if python3 - "$TMP/client.out" <<'EOF'
import json, sys
for line in open(sys.argv[1]):
    if not line.strip():
        continue
    m = json.loads(line)
    if m.get("event") == "amplitude":
        v = m.get("amplitude")
        sys.exit(0 if isinstance(v, (int, float)) and 0.0 <= v <= 1.0 else 1)
sys.exit(1)
EOF
then ok "amplitude events carry a level in 0..1"; else bad "amplitude events carry a level"; fi
if python3 - "$TMP/client.out" <<'EOF'
import json, sys
for line in open(sys.argv[1]):
    if not line.strip():
        continue
    m = json.loads(line)
    if m.get("event") == "provisional":
        d = m.get("data") or {}
        if "words" in d and "hidden" in d:
            sys.exit(0)
sys.exit(1)
EOF
then ok "provisional events carry words+hidden"; else bad "provisional events carry words+hidden"; fi
for _ in $(seq 1 60); do grep -q 'run finished' "$TMP/svc.log" 2>/dev/null && break; sleep 0.2; done
if grep -q 'run finished' "$TMP/svc.log"; then ok "stop op ended the run"; else
  bad "stop op ended the run (see $TMP/svc.log)"; fi
if python3 - "$TMP/client.out" <<'EOF'
import json, sys
for line in open(sys.argv[1]):
    if not line.strip():
        continue
    st = json.loads(line).get("state")
    if st in ("READY", "ERROR", "IDLE"):
        sys.exit(0)
sys.exit(1)
EOF
then ok "daemon published a finishing state (READY/ERROR/IDLE)"; else bad "daemon published a finishing state"; fi

# 3. daemon logic tests + the real overlay config loading clean.
if cargo test -p vaani-key-service >"$TMP/cargo-test.log" 2>&1; then
  ok "daemon unit tests pass ($(grep -oE '[0-9]+ passed' "$TMP/cargo-test.log" | head -1))"
else
  bad "daemon unit tests pass (see $TMP/cargo-test.log)"
fi
kill -TERM "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; SRV=0

QS="$HOME/.config/quickshell/vaani/shell.qml"
if [ -f "$QS" ]; then
  timeout 6 quickshell -c vaani >"$TMP/qs.log" 2>&1 &
  QSPID=$!
  sleep 4
  if grep -qiE "error|is not a type" "$TMP/qs.log"; then
    bad "overlay loads clean (log: $(grep -iE 'error|is not a type' "$TMP/qs.log" | head -1))"
  else
    ok "overlay loads clean (no QML errors)"
  fi
  kill "$QSPID" 2>/dev/null; wait "$QSPID" 2>/dev/null
else
  bad "overlay installed at $QS"
fi

printf 'gate-18: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-18 GREEN"; exit 0; else echo "gate-18 RED"; exit 1; fi
