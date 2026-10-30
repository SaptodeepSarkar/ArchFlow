#!/usr/bin/env bash
# CI gate set: everything that runs on a plain Linux box with Rust + python3.
#
# The full board (`./TESTS/gate.sh`) is 22/22 on the real machine, but most of
# it needs hardware: a microphone and PipeWire (04/05/13/14), a compositor with
# wtype and quickshell (06/08/17/18), NVIDIA VRAM (05/09), systemd (15), and a
# local formatter LLM (19's live half). Those stay local/on-box gates.
#
# This script is the honest subset for CI: pure logic, fixtures and contracts,
# plus gate 22, which runs the real daemon end-to-end against stub mic/STT/typing
# backends (no mic, no compositor, no GPU, no model server).
set -u -o pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
step() { printf '\n== %s\n' "$1"; }
note() { printf '   %s\n' "$1"; }
bad()  { printf '   FAIL: %s\n' "$1"; fail=1; }

step "shell syntax"
for f in install.sh TESTS/gate.sh TESTS/gates/*.sh packaging/vaani-trigger \
         packaging/serve-formatter.sh packaging/serve-refine-stt.sh \
         packaging/dev-run.sh; do
  if bash -n "$f" 2>/dev/null; then note "ok $f"; else bad "syntax error in $f"; bash -n "$f"; fi
done
# Gate 20 (the fine-tuned two-pass path) needs vosk, so it stays off the
# hermetic list like gate 18 -- but the scripts it drives are still parsed here
# with ast, which writes nothing.
for f in crates/stt-manager/backend/transcribe.py \
         crates/stt-manager/backend/refine_whisper.py packaging/serve-refine-stt.py; do
  if python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$f" 2>/dev/null; then
    note "ok $f"
  else
    bad "python syntax error in $f"
    python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$f"
  fi
done
# The repetition guards are pure functions with no model behind them, so they
# are checked here instead of on a box with GPU weights.
if python3 TESTS/test_stt_guard.py >/tmp/ci-stt-guard.log 2>&1; then
  note "$(tail -1 /tmp/ci-stt-guard.log)"
else
  bad "stt repetition guard"
  tail -10 /tmp/ci-stt-guard.log
fi

step "rust: build + tests (whole workspace)"
if cargo build --workspace --quiet; then note "workspace builds"; else bad "workspace build"; fi
# Capture to a file, not a pipe: `cargo test | tail` reports tail's status,
# so a failing test would sail through CI.
TEST_LOG="/tmp/ci-cargo-test.log"
if cargo test --workspace >"$TEST_LOG" 2>&1; then
  note "workspace tests: $(grep -c '^test result: ok' "$TEST_LOG") targets, \
$(grep -oE '^test result: ok. [0-9]+ passed' "$TEST_LOG" | grep -oE '[0-9]+' | awk '{s+=$1} END {print s+0}') tests passed"
else
  bad "workspace tests"
  grep -E '^test .* FAILED|panicked|^error' "$TEST_LOG" | head -15
fi

step "hermetic gates"
for g in 01 02 07 10 11 12 19 22; do
  case "$g" in
    01) cmd="python3 TESTS/test_fixtures.py" ;;
    22) cmd="./TESTS/gates/gate-22-e2e.sh" ;;
    *)  cmd="./TESTS/gates/gate-$g.sh" ;;
  esac
  if $cmd >"/tmp/ci-gate-$g.log" 2>&1; then
    note "gate $g GREEN"
  else
    bad "gate $g RED (see below)"
    tail -15 "/tmp/ci-gate-$g.log"
  fi
done

printf '\n'
if [ "$fail" -eq 0 ]; then echo "ci.sh: GREEN (hermetic set)"; exit 0; fi
echo "ci.sh: RED"
exit 1
