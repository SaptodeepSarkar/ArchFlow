#!/usr/bin/env bash
# Phase 02 gate (config-parse): sample parses, round-trips, broken conf is
# handled without crashing, missing file yields documented defaults.
# Exits 0 (GREEN) only if every check passes.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

SAMPLE="TESTS/fixtures/config-sample.conf"
TMP="$(mktemp -d /tmp/vaani-gate02.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# 1. crate builds
if cargo build -p vaani-config >"$TMP/build.log" 2>&1; then
  ok "vaani-config builds"
else
  bad "vaani-config builds (see $TMP/build.log)"
fi

# 2. unit tests
if cargo test -p vaani-config >"$TMP/test.log" 2>&1; then
  ok "cargo test -p vaani-config passes"
else
  bad "cargo test fails (see $TMP/test.log)"
fi

# 3. sample parses with documented values, no warnings
cargo run -q -p vaani-config --example dump -- "$SAMPLE" \
  >"$TMP/sample.out" 2>"$TMP/sample.err"
code=$?
if [ $code -eq 0 ] \
  && grep -q '^ui_words = 4$' "$TMP/sample.out" \
  && grep -q '^stt_model = small.en$' "$TMP/sample.out" \
  && grep -q '^stt_fallback_model = base.en$' "$TMP/sample.out" \
  && grep -q '^idle_timeout_s = 120$' "$TMP/sample.out" \
  && grep -q '^saptodeep = Saptodeep Sarkar$' "$TMP/sample.out" \
  && grep -q '^github = https://github.com/SaptodeepSarkar$' "$TMP/sample.out" \
  && [ ! -s "$TMP/sample.err" ]; then
  ok "sample conf parses with documented values, zero warnings"
else
  bad "sample conf parses (exit=$code, see $TMP/sample.out $TMP/sample.err)"
fi

# 4. sample round-trips identical
if cargo run -q -p vaani-config --example dump -- --roundtrip "$SAMPLE" \
    >"$TMP/rt.out" 2>"$TMP/rt.err" \
  && grep -q '^ROUNDTRIP-OK$' "$TMP/rt.out"; then
  ok "sample round-trips identical"
else
  bad "sample round-trip (see $TMP/rt.out $TMP/rt.err)"
fi

# 5. broken conf: warnings on stderr, exit 0, sane fallbacks
cat >"$TMP/broken.conf" <<'EOF'
bogus_key = 1
ui_words = not-a-number
this line has no equals
idle_timeout_s = -5
[wat]
x = y
[names]
alice = Alice Liddell
EOF
cargo run -q -p vaani-config --example dump -- "$TMP/broken.conf" \
  >"$TMP/broken.out" 2>"$TMP/broken.err"
code=$?
nwarnings=$(grep -c '^warning: ' "$TMP/broken.err" || true)
if [ "$code" -eq 0 ] \
  && [ "$nwarnings" -ge 5 ] \
  && grep -q '^ui_words = 4$' "$TMP/broken.out" \
  && grep -q '^idle_timeout_s = 120$' "$TMP/broken.out" \
  && grep -q '^alice = Alice Liddell$' "$TMP/broken.out"; then
  ok "broken conf handled: exit 0, $nwarnings warnings, defaults kept"
else
  bad "broken conf handled (exit=$code warnings=$nwarnings, see $TMP/broken.out $TMP/broken.err)"
fi

# 6. missing file -> documented defaults, no crash
cargo run -q -p vaani-config --example dump -- "$TMP/does-not-exist.conf" \
  >"$TMP/missing.out" 2>"$TMP/missing.err"
code=$?
if [ "$code" -eq 0 ] \
  && grep -q '^ui_words = 4$' "$TMP/missing.out" \
  && grep -q '^stt_model = small.en$' "$TMP/missing.out" \
  && grep -q '^idle_timeout_s = 120$' "$TMP/missing.out"; then
  ok "missing file yields documented defaults"
else
  bad "missing file defaults (exit=$code, see $TMP/missing.out $TMP/missing.err)"
fi

printf 'gate-02: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-02 GREEN"; exit 0; else echo "gate-02 RED"; exit 1; fi
