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
    05) exec gates/gate-05.sh ;;
    06) exec gates/gate-06.sh ;;
    07) exec gates/gate-07.sh ;;
    08) exec gates/gate-08.sh ;;
    09) exec gates/gate-09.sh ;;
    10) exec gates/gate-10.sh ;;
    11) exec gates/gate-11.sh ;;
    12) exec gates/gate-12.sh ;;
    13) exec gates/gate-13.sh ;;
    14) exec gates/gate-14.sh ;;
    15) exec gates/gate-15.sh ;;
    16) exec gates/gate-16.sh ;;
    *) echo "gate $1 not implemented yet"; exit 2 ;;
  esac
}

if [ $# -eq 1 ]; then run_one "$1"; fi

echo "gates:"
gate 01 fixtures-contracts "python3 test_fixtures.py"
gate 02 config-parse "gates/gate-02.sh"
gate 03 hotkey-idle "gates/gate-03.sh"
gate 04 audio-helper "gates/gate-04.sh"
gate 05 stt-stream "gates/gate-05.sh"
gate 06 pill-ui "gates/gate-06.sh"
gate 07 llm-format "gates/gate-07.sh"
gate 08 typing "gates/gate-08.sh"
gate 09 key-lifecycle "gates/gate-09.sh"
gate 10 timeouts-offload "gates/gate-10.sh"
gate 11 cancel-error "gates/gate-11.sh"
gate 12 names-links "gates/gate-12.sh"
gate 13 integration "gates/gate-13.sh"
gate 14 soak "gates/gate-14.sh"
gate 15 packaging "gates/gate-15.sh"
gate 16 harden-release "gates/gate-16.sh"
