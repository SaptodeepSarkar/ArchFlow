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
    17) exec gates/gate-17.sh ;;
    18) exec gates/gate-18.sh ;;
    *) echo "gate $1 not implemented yet"; exit 2 ;;
  esac
}

if [ $# -eq 1 ]; then run_one "$1"; fi

GATES='01|fixtures-contracts|python3 test_fixtures.py
02|config-parse|gates/gate-02.sh
03|hotkey-idle|gates/gate-03.sh
04|audio-helper|gates/gate-04.sh
05|stt-stream|gates/gate-05.sh
06|pill-ui|gates/gate-06.sh
07|llm-format|gates/gate-07.sh
08|typing|gates/gate-08.sh
09|key-lifecycle|gates/gate-09.sh
10|timeouts-offload|gates/gate-10.sh
11|cancel-error|gates/gate-11.sh
12|names-links|gates/gate-12.sh
13|integration|gates/gate-13.sh
14|soak|gates/gate-14.sh
15|packaging|gates/gate-15.sh
17|live-pipeline|gates/gate-17.sh
18|live-ui|gates/gate-18.sh'

run_gates() { # $1 = specs, one per line as nn|name|command
  local nn name cmd
  while IFS='|' read -r nn name cmd; do
    [ -n "${nn:-}" ] || continue
    if eval "$cmd" >/tmp/vaani-gate-"$nn".log 2>&1; then
      echo "$nn|$name|GREEN"
    else
      echo "$nn|$name|RED"
    fi
  done <<<"$1"
}

echo "gates:"
{
  run_gates "$GATES"
  # gate 16 is the docs-match meta-gate: it reads every other gate's log, so
  # it runs last, after 17/18, and its own line still prints in numeric order.
  run_gates "16|harden-release|gates/gate-16.sh"
} | sort -n | while IFS='|' read -r nn name status; do
  if [ "$status" = "GREEN" ]; then
    printf "  %s %-18s GREEN\n" "$nn" "$name"
  else
    printf "  %s %-18s RED (see /tmp/vaani-gate-%s.log)\n" "$nn" "$name" "$nn"
  fi
done
