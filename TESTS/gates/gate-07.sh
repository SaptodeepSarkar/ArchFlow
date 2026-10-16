#!/usr/bin/env bash
# Phase 07 gate (llm-format): formatter scores 20/20 exact match on
# TESTS/fixtures/formatting.json, p95 under 300ms, model unloaded after.
# Exits 0 (GREEN) only if every check passes.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TMP="$(mktemp -d /tmp/vaani-gate07.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# 1. crate builds
if cargo build -p llm-formatter >"$TMP/build.log" 2>&1; then
  ok "llm-formatter builds"
else
  bad "llm-formatter builds (see $TMP/build.log)"
fi

# 2. unit tests (include the 20-pair contract exact-match test)
if cargo test -p llm-formatter >"$TMP/test.log" 2>&1; then
  ok "cargo test -p llm-formatter passes"
else
  bad "cargo test fails (see $TMP/test.log)"
fi

# 3+4. 20/20 exact match + p95 latency, measured per fixture on the binary.
BIN="$ROOT/target/debug/llm-format"
if [ ! -x "$BIN" ]; then
  bad "binary $BIN missing"
else
  if python3 - "$BIN" >"$TMP/score.log" 2>&1 <<'EOF'; then
import json, subprocess, sys, time
fx = json.load(open("TESTS/fixtures/formatting.json"))
lat, fails = [], []
for p in fx:
    t0 = time.perf_counter()
    r = subprocess.run([sys.argv[1]], input=(p["raw"] + "\n").encode(),
                       capture_output=True, timeout=10)
    dt = (time.perf_counter() - t0) * 1000.0
    lat.append(dt)
    got = r.stdout.decode().strip()
    if got != p["expected"]:
        fails.append((p["id"], p["raw"], p["expected"], got))
lat.sort()
p95 = lat[max(0, (len(lat) * 95 + 99) // 100 - 1)]
score = len(fx) - len(fails)
print(f"score: {score}/{len(fx)}")
print(f"p50: {lat[len(lat)//2]:.2f}ms p95: {p95:.2f}ms max: {lat[-1]:.2f}ms")
for f in fails:
    print(f"FAIL {f[0]}: raw={f[1]!r} want={f[2]!r} got={f[3]!r}")
ok = score == len(fx) and p95 < 300.0
print("SCORE-OK" if score == len(fx) else "SCORE-FAIL")
print("P95-OK" if p95 < 300.0 else "P95-FAIL")
sys.exit(0 if ok else 1)
EOF
    ok "20/20 exact match, p95 under 300ms ($(grep -E '^p50' "$TMP/score.log"))"
  else
    bad "score/latency gate (see $TMP/score.log: $(head -3 "$TMP/score.log" | tr '\n' ' '))"
  fi
  cat "$TMP/score.log"
fi

# 5. model unloaded after: no llama runtime of OURS resident (bracket
# trick so this check can never match its own shell), ...
if pgrep -f '[l]lama-server|[l]lama_cpp|[l]lama-cpp' >/dev/null 2>&1; then
  bad "llama runtime still resident after run"
else
  ok "no llama runtime resident after run"
fi
# ...and no Vaani process holding VRAM (machine-wide GPU is shared with
# the desktop; a foreign occupant must not fail this gate).
if command -v nvidia-smi >/dev/null 2>&1; then
  VHOLD=""
  for p in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null); do
    if tr '\0' ' ' </proc/"$p"/cmdline 2>/dev/null | grep -qE 'llm-format|target/debug|vaani'; then
      VHOLD="$VHOLD $p"
    fi
  done
  if [ -z "$VHOLD" ]; then
    ok "no Vaani process holds VRAM"
  else
    bad "Vaani process still holds VRAM: pids$VHOLD"
  fi
else
  ok "nvidia-smi absent, GPU check skipped (nothing was ever loaded)"
fi

printf 'gate-07: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-07 GREEN"; exit 0; else echo "gate-07 RED"; exit 1; fi
