#!/usr/bin/env bash
# Vaani phase gates. Usage: gate.sh [NN]. No args lists gate status.
set -u
cd "$(dirname "$0")"

gate() { # $1=nn $2=name $3=command (empty = pending)
  if [ -z "${3:-}" ]; then printf "  %s %-18s PENDING\n" "$1" "$2"; return 0; fi
  if eval "$3" >/tmp/vaani-gate-"$1".log 2>&1; then printf "  %s %-18s GREEN\n" "$1" "$2"; else printf "  %s %-18s RED (see /tmp/vaani-gate-%s.log)\n" "$1" "$2" "$1"; fi
}

run_one() {
  case "$1" in
    01) exec python3 test_fixtures.py ;;
    02) exec gates/gate-02.sh ;;
    03) exec gates/gate-03.sh ;;
    04) exec gates/gate-04.sh ;;
    06) exec gates/gate-06.sh ;;
    *) echo "gate $1 not implemented yet"; exit 2 ;;
  esac
}

if [ $# -eq 1 ]; then run_one "$1"; fi

echo "gates:"
gate 01 fixtures-contracts "python3 test_fixtures.py"
gate 02 config-parse "gates/gate-02.sh"
gate 03 hotkey-idle "gates/gate-03.sh"
gate 04 audio-helper "gates/gate-04.sh"
gate 05 stt-stream ""
gate 06 pill-ui "gates/gate-06.sh"
gate 07 llm-format ""
gate 08 typing ""
gate 09 key-lifecycle ""
gate 10 timeouts-offload ""
gate 11 cancel-error ""
gate 12 names-links ""
gate 13 integration ""
gate 14 soak ""
gate 15 packaging ""
gate 16 harden-release ""
