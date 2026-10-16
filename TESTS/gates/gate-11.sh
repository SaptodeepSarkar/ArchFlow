#!/usr/bin/env bash
# Gate 11 (cancel-error): walk all 6 cancel/error paths in the pure
# decision module; GREEN only if each ends idle with zero residents.
# Live-daemon proof is Phase 13/14's job — this gate proves the table.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate11.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

MOD="crates/key-service/src/cancel.rs"
[ -f "$MOD" ] || { bad "module $MOD exists"; printf 'gate-11: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-11 RED"; exit 1; }
ok "module $MOD exists"

# 1. std-only: no extern crate / use of sibling crates.
if grep -Eq '^\s*(use (vaani|tokio|serde)|extern crate)' "$MOD"; then
  bad "module is std-only (found external dep)"
else
  ok "module is std-only"
fi

# 2. decision table covers all 6 paths.
for sym in Cancel SttLoadFail LlmLoadFail MicFail ignore_trigger skip_formatting offload_all; do
  grep -q "$sym" "$MOD" || { bad "table mentions $sym"; break; }
done
[ "$fail" -eq 0 ] && ok "decision table covers all 6 paths"

# 3. compile the module's own tests and walk every path.
if rustc --edition=2021 --test "$MOD" -o "$TMP/cancel-test" >"$TMP/build.log" 2>&1; then
  ok "cancel module test binary builds"
else
  bad "cancel module test binary builds (see $TMP/build.log)"; cat "$TMP/build.log"
fi

if [ -x "$TMP/cancel-test" ]; then
  if "$TMP/cancel-test" >"$TMP/test.log" 2>&1; then
    ok "module tests pass"
  else
    bad "module tests pass (see $TMP/test.log)"; cat "$TMP/test.log"
  fi
  # 4. each of the 6 named paths ran and passed.
  for t in cancel_mid_listen cancel_mid_transcribe stt_load_fail llm_load_fail mic_fail double_trigger_ignored_then_idle_clean; do
    if grep -q "test tests::$t ... ok" "$TMP/test.log"; then
      ok "path walked: $t"
    else
      bad "path walked: $t"
    fi
  done
  # 5. no failures overall.
  grep -q "test result: ok" "$TMP/test.log" && ok "zero test failures" || bad "zero test failures"
fi

printf 'gate-11: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-11 GREEN"; exit 0; else echo "gate-11 RED"; exit 1; fi
