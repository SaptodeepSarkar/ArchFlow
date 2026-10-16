#!/usr/bin/env bash
# Gate 06 (pill-ui): exits 0 only if qmllint is clean, all 4 states + cancel
# are present and wired, and the stub event driver passes.
set -u
cd "$(dirname "$0")"/../..
QML=UI/quickshell/shell.qml
FAIL=0

say() { printf '%s\n' "$1"; }

if qmllint "$QML" >/tmp/vaani-gate-06-qmllint.log 2>&1; then
  say "gate-06: qmllint clean"
else
  say "gate-06: qmllint FAILED (see /tmp/vaani-gate-06-qmllint.log)"; FAIL=1
fi

for s in STARTING RECORDING TRANSCRIBING CLEANING INSERTING READY CANCELLED IDLE ERROR; do
  if grep -q "\"$s\"" "$QML"; then say "gate-06: state $s present";
  else say "gate-06: state $s MISSING"; FAIL=1; fi
done

if grep -q 'sendOp("stop")' "$QML" && grep -q "/vaani/control.sock" "$QML"; then
  say "gate-06: stop op wired over the control socket"
else
  say "gate-06: stop/socket wiring MISSING"; FAIL=1
fi

if python3 TESTS/drivers/pill_events.py; then
  say "gate-06: driver passed"
else
  say "gate-06: driver FAILED"; FAIL=1
fi

if [ "$FAIL" -eq 0 ]; then say "GATE 06 GREEN"; else say "GATE 06 RED"; fi
exit "$FAIL"
