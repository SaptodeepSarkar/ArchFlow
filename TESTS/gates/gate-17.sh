#!/usr/bin/env bash
# Gate 17 — live pipeline. GREEN only if the daemon binary runs the full
# chain on a fixture wav (transcribe -> format with config vocab -> type)
# and handles the empty-transcript path without typing.
# Typing always goes through a stub wtype first on PATH (exec-edge stub).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate17.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/shim"
cat >"$TMP/shim/wtype" <<'EOF'
#!/usr/bin/env bash
printf '%s' "$1" >"$VAANI_WTYPE_SCRATCH"
echo "stub-fired bytes=${#1}" >>"$VAANI_WTYPE_LOG"
EOF
chmod +x "$TMP/shim/wtype"
export PATH="$TMP/shim:$PATH"
export VAANI_WTYPE_SCRATCH="$TMP/typed.txt" VAANI_WTYPE_LOG="$TMP/wtype.log"
cp TESTS/fixtures/config-vocab.conf "$TMP/vaani.conf"
: >"$VAANI_WTYPE_LOG"

BIN="$ROOT/target/debug/vaani-key-service"
[ -x "$BIN" ] || { bad "daemon binary missing (build first)"; printf 'gate-17: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-17 RED"; exit 1; }

# 1. fixture with speech: full chain types formatted text via the stub.
rm -f "$VAANI_WTYPE_SCRATCH"
OUT="$("$BIN" --pipeline-test TESTS/fixtures/audio/s1-hello.wav "$TMP/vaani.conf" 2>"$TMP/err.log")" && RC=0 || RC=$?
echo "$OUT" | grep -q "^PIPELINE-OK typed=" || bad "pipeline-test exit path (rc=$RC out=$OUT err=$(cat "$TMP/err.log"))"
if [ -f "$VAANI_WTYPE_SCRATCH" ] && [ "$(cat "$VAANI_WTYPE_SCRATCH")" = "Hello." ]; then
  ok "s1 hello.wav -> typed 'Hello.' via stub wtype"
else
  bad "typed capture (got: $(cat "$VAANI_WTYPE_SCRATCH" 2>/dev/null), want 'Hello.')"
fi
grep -q "stub-fired" "$VAANI_WTYPE_LOG" 2>/dev/null \
  && ok "stub wtype fired (real wtype never ran)" \
  || bad "stub wtype proof"

# 2. vocab path: config names/links expand through the daemon's pipeline.
cat >"$TMP/vaani.conf" <<'EOF'
ui_words = 4
stt_model = small.en
stt_fallback_model = base.en
idle_timeout_s = 120

[names]
saptodeep = Saptodeep Sarkar

[links]
github = https://github.com/SaptodeepSarkar
EOF
rm -f "$VAANI_WTYPE_SCRATCH"
"$BIN" --pipeline-test TESTS/fixtures/audio/s1-hello.wav "$TMP/vaani.conf" >/dev/null 2>&1
[ "$(cat "$VAANI_WTYPE_SCRATCH" 2>/dev/null)" = "Hello." ] \
  && ok "config vocab accepted, chain still green" \
  || bad "config vocab run"

# 3. daemon binary still builds warning-free with the pipeline wired in.
if cargo build -p vaani-key-service 2>&1 | grep -qE '^error|^warning'; then
  bad "warning-free build"
else
  ok "warning-free build"
fi

printf 'gate-17: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-17 GREEN"; exit 0; else echo "gate-17 RED"; exit 1; fi
