#!/usr/bin/env bash
# CI gate set: everything that runs on a plain Linux box with Rust + python3.
#
# The full board (`./TESTS/gate.sh`) is 19/19 on the real machine, but most of
# it needs hardware: a microphone and PipeWire (04/05/13/14), a compositor with
# wtype and quickshell (06/08/17/18), NVIDIA VRAM (05/09), systemd (15), and a
# local formatter LLM (19's live half). Those stay local/on-box gates.
#
# This script is the honest subset for CI: pure logic, fixtures and contracts.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
step() { printf '\n== %s\n' "$1"; }
note() { printf '   %s\n' "$1"; }
bad()  { printf '   FAIL: %s\n' "$1"; fail=1; }

step "shell syntax"
for f in install.sh TESTS/gate.sh TESTS/gates/*.sh packaging/vaani-trigger; do
  if bash -n "$f" 2>/dev/null; then note "ok $f"; else bad "syntax error in $f"; bash -n "$f"; fi
done

step "rust: build + tests (whole workspace)"
if cargo build --workspace --quiet; then note "workspace builds"; else bad "workspace build"; fi
if cargo test --workspace --quiet 2>&1 | tail -25; then note "workspace tests"; else bad "workspace tests"; fi

step "hermetic gates"
for g in 01 02 07 10 11 12 19; do
  case "$g" in
    01) cmd="python3 TESTS/test_fixtures.py" ;;
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
