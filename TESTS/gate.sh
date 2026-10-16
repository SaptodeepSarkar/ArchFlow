#!/usr/bin/env bash
# Vaani phase gates. Usage: gate.sh [NN]. No args lists gate status.
set -u
cd "$(dirname "$0")"

gate() { # $1=nn $2=name $3=command (empty = pending)
  if [ -z "${3:-}" ]; then printf "  %s %-14s PENDING\n" "$1" "$2"; return 0; fi
  if eval "$3" >/tmp/vaani-gate-"$1".log 2>&1; then printf "  %s %-14s GREEN\n" "$1" "$2"; else printf "  %s %-14s RED (see /tmp/vaani-gate-%s.log)\n" "$1" "$2" "$1"; fi
}

run_one() {
  case "$1" in
    01) exec python3 test_fixtures.py ;;
    *) echo "gate $1 not implemented yet"; exit 2 ;;
  esac
}

if [ $# -eq 1 ]; then run_one "$1"; fi

echo "gates:"
gate 01 fixtures "python3 test_fixtures.py"
gate 02 hotkey ""
gate 03 audio ""
gate 04 stt ""
gate 05 format ""
gate 06 typing ""
gate 07 pill ""
gate 08 e2e-offload ""
