#!/usr/bin/env bash
# Gate 20 — fine-tuned two-pass STT. GREEN only if the pipeline can run the
# end-of-utterance re-decode:
#   1. the re-decode client ships, is stdlib-only, and speaks the same line
#      protocol as the streaming backend,
#   2. the daemon's second pass replaces the streaming words when the backend
#      answers, and
#   3. every failure mode keeps the streaming words instead of losing the
#      utterance (empty answer, dead server, no backend configured).
#
# Hermetic on purpose: a stub HTTP server and stub backend scripts stand in for
# the fine-tuned model, so this runs in CI with no GPU, no model weights and no
# microphone. The real weights are exercised by `vaani-key-service --refine-test`
# on a box that has them (see the build log).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate20.XXXXXX)"
SRV=0
cleanup() {
  [ "$SRV" -ne 0 ] && kill -KILL "$SRV" 2>/dev/null
  rm -rf "$TMP"
}
trap cleanup EXIT

BIN="$ROOT/target/debug/vaani-key-service"
CLIENT="$ROOT/crates/stt-manager/backend/refine_whisper.py"
SERVER="$ROOT/packaging/serve-refine-stt.py"
WAV="$ROOT/TESTS/fixtures/audio/s1-hello.wav"
PY="${VAANI_STT_PYTHON:-/home/saptodeep/Projects/Kyuma/.venv/bin/python}"
MODEL="${VAANI_STT_MODEL:-/home/saptodeep/Projects/Kyuma/models/vosk-model-small-en-us-0.15}"

for f in "$BIN" "$CLIENT" "$SERVER" "$WAV"; do
  [ -e "$f" ] && ok "present: $(basename "$f")" || bad "missing: $f"
done
if [ "$fail" -ne 0 ]; then
  printf 'gate-20: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-20 RED"; exit 1
fi
if [ -x "$PY" ] && [ -d "$MODEL" ]; then ok "STT python/model present"; else
  bad "STT python/model present (py=$PY model=$MODEL)"
  printf 'gate-20: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-20 RED"; exit 1
fi

# 1. The server must stay importable without the ML stack: it defers torch /
#    transformers / numpy / peft to call time, so a packaging check (or --help)
#    works on a bare box.
if python3 "$SERVER" --help >"$TMP/help.log" 2>&1; then
  ok "re-decode server imports without the ML stack (--help)"
else
  bad "re-decode server --help (see below)"; sed -n '1,3p' "$TMP/help.log"
fi
if grep -q "default: 8083" "$TMP/help.log"; then
  ok "server's default port matches the daemon's default endpoint"
else
  bad "server default port is 8083"
fi

# 2. Client protocol, against a stub server that answers like the real one.
#    Bind port 0 so the test cannot collide with a real server.
python3 - "$TMP/port" <<'EOF' &
import http.server, json, sys
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        if n == 0:
            self.send_response(400); self.end_headers(); return
        body = json.dumps({"text": "stub words here",
                           "words": [{"w": "stub", "t": 0.0}, {"w": "words", "t": 0.0},
                                     {"w": "here", "t": 0.0}],
                           "audio": 1.0, "infer": 0.01}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
open(sys.argv[1], "w").write(str(srv.server_address[1]))
srv.serve_forever()
EOF
SRV=$!
for _ in $(seq 1 40); do [ -s "$TMP/port" ] && break; sleep 0.1; done
PORT="$(cat "$TMP/port" 2>/dev/null || echo)"
if [ -n "$PORT" ]; then
  python3 - "$WAV" "$TMP/pcm.raw" <<'EOF'
import sys, wave
w = wave.open(sys.argv[1], "rb")
open(sys.argv[2], "wb").write(w.readframes(w.getnframes()))
EOF
  OUT="$(VAANI_STT_REFINE_ENDPOINT="http://127.0.0.1:$PORT" "$PY" "$CLIENT" --stdin \
    <"$TMP/pcm.raw" 2>"$TMP/client.err")"
  RC=$?
  if [ "$RC" -eq 0 ] && [ "$(printf '%s' "$OUT" | grep -c '^W ')" -eq 3 ]; then
    ok "client emits one W line per word ($(printf '%s' "$OUT" | tr '\n' ' '))"
  else
    bad "client emits W lines (rc=$RC out=$OUT err=$(head -1 "$TMP/client.err"))"
  fi
  if printf '%s' "$OUT" | grep -q "^DONE .*words=3 .*model=http://127.0.0.1:$PORT$"; then
    ok "client ends with DONE carrying counts + endpoint"
  else
    bad "client DONE line correct"
  fi
else
  bad "stub server failed to report a port"
fi
kill -KILL "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null; SRV=0

# 3. A dead server must fail loudly (exit nonzero) so the daemon falls back.
if VAANI_STT_REFINE_ENDPOINT="http://127.0.0.1:1" "$PY" "$CLIENT" --stdin \
  <"$TMP/pcm.raw" >/dev/null 2>"$TMP/dead.err"; then
  bad "client fails when the server is unreachable"
else
  ok "client fails when the server is unreachable"
fi

# 4. Stub backends for the daemon's second pass. The daemon only cares about
#    env + script path, so this proves the wiring without any model. They must
#    be *python* scripts: run_stdin always executes the backend with the STT
#    python, exactly like transcribe.py.
cat >"$TMP/stub_ok.py" <<'EOF'
import os
import sys

sys.stdin.buffer.read()
print("W 0.00 frobnicated")
print("W 0.10 utterance")
print("DONE audio=1.00 infer=0.01 words=2 model=%s"
      % os.environ.get("VAANI_STT_REFINE_ENDPOINT", ""))
EOF
cat >"$TMP/stub_fail.py" <<'EOF'
import sys

sys.stdin.buffer.read()
print("stub backend exploded", file=sys.stderr)
sys.exit(1)
EOF

OUT="$(VAANI_STT_REFINE_BACKEND="$TMP/stub_ok.py" "$BIN" --refine-test "$WAV" 2>&1)"
if printf '%s' "$OUT" | grep -q 'REFINE-OK' && printf '%s' "$OUT" | grep -q 'refined="frobnicated utterance"' \
  && printf '%s' "$OUT" | grep -q 'changed=true'; then
  ok "second pass replaces the streaming words ($OUT)"
else
  bad "second pass replaces the streaming words (got: $OUT)"
fi
if printf '%s' "$OUT" | grep -q 'streaming="'; then
  ok "streaming words are still reported for comparison"
else
  bad "streaming words reported"
fi

VAANI_STT_REFINE_BACKEND="$TMP/stub_fail.py" "$BIN" --refine-test "$WAV" >"$TMP/fail.log" 2>&1
if [ $? -ne 0 ] && grep -q 'REFINE-FAIL' "$TMP/fail.log"; then
  ok "a broken second pass reports failure instead of pretending"
else
  bad "a broken second pass reports failure (got: $(tail -1 "$TMP/fail.log"))"
fi

# 5. Opt-in by default: no env, no second pass.
env -u VAANI_STT_REFINE_BACKEND -u VAANI_STT_REFINE_ENDPOINT \
  "$BIN" --refine-test "$WAV" >"$TMP/off.log" 2>&1
if [ $? -ne 0 ] && grep -q 'no refine backend configured' "$TMP/off.log"; then
  ok "second pass stays off unless a backend is configured"
else
  bad "second pass is opt-in (got: $(tail -1 "$TMP/off.log"))"
fi

# 6. The fallback itself is pure logic, covered by unit tests: refined words
#    win, empty/whitespace answers fall back to streaming, both-empty types
#    nothing.
if cargo test -p stt-manager -p vaani-key-service >"$TMP/unit.log" 2>&1 \
  && grep -q 'refined_words_replace_streaming_but_never_vanish ... ok' "$TMP/unit.log" \
  && grep -q 'silence_is_never_re_decoded ... ok' "$TMP/unit.log" \
  && grep -q 'refine_stays_off_unless_a_real_script_is_configured ... ok' "$TMP/unit.log" \
  && grep -q 'bytes_to_pcm_pairs_little_endian_and_drops_a_stray_byte ... ok' "$TMP/unit.log"; then
  ok "two-pass unit tests pass (fallback, opt-in default, silence guard, PCM pairing)"
else
  bad "two-pass unit tests pass (see $TMP/unit.log)"
fi

printf 'gate-20: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-20 GREEN"; exit 0; else echo "gate-20 RED"; exit 1; fi
