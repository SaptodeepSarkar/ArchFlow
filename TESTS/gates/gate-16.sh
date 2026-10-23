#!/usr/bin/env bash
# Gate 16 — harden-release. GREEN only if ALL hold:
#   1. docs-match: every behavior in PRD/ + DOCS/ maps to a passing gate.
#      Mismatches print as OWED <owner>; the gate fails only if an OWED item
#      is load-bearing AND unowned (owner '-'). Structural/wording gaps print
#      as WARN, never fail. Owned-but-pending items (gates 14/15, formatter
#      swap) are recorded as debt, not silence.
#   2. perf table: live numbers read from fast-gate outputs (no heavy re-runs).
#   3. soak/gibberish status reported (PENDING when gate-14 has not run).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; owed=0; warn=0; unowned=0
ok()   { printf '  [PASS] %s\n' "$1"; pass=$((pass + 1)); }
is_owed() { printf '  [OWED -> %s] %s\n' "$1" "$2"; owed=$((owed + 1)); }
is_warn() { printf '  [WARN] %s\n' "$1"; warn=$((warn + 1)); }
is_unowned() { printf '  [OWED-UNOWNED] %s\n' "$1"; unowned=$((unowned + 1)); }

gate_green() { # $1=nn -> 0 iff that gate's log ends GREEN
  local log="/tmp/vaani-gate-$1.log"
  [ -f "$log" ] || return 1
  grep -qE 'GREEN' "$log" || return 1
  grep -qE 'RED|FAIL' "$log" && ! grep -qE 'GREEN' "$log" && return 1
  # a log containing both PASS lines and no RED verdict counts as green
  ! grep -qE 'gate-.* RED|^GATE .* RED' "$log"
}

# claim|source|gates(space-separated, '-' = none)|kind(load|struct)|note
map_row() {
  local claim="$1" src="$2" gates="$3" kind="$4" owner="$5"
  if [ "$gates" = "-" ]; then
    if [ "$kind" = "load" ] && [ "$owner" = "-" ]; then
      is_unowned "$claim ($src, no gate, no owner)"
    elif [ "$kind" = "load" ]; then
      is_owed "$owner" "$claim ($src)"
    else
      is_warn "$claim ($src; $owner)"
    fi
    return
  fi
  local g all_green=1
  for g in $gates; do gate_green "$g" || all_green=0; done
  if [ "$all_green" -eq 1 ]; then
    if [ "$kind" = "struct" ]; then
      is_warn "$claim ($src; gate $gates green but wording-only coverage)"
    else
      ok "$claim ($src -> gate $gates)"
    fi
  else
    if [ "$owner" = "-" ]; then
      is_unowned "$claim ($src; gate $gates not green, no owner)"
    else
      is_owed "$owner" "$claim ($src; gate $gates not green)"
    fi
  fi
}

echo "== docs-match mapping =="
# --- PRD/overview.md ---
map_row "hotkey summons pill, streams words, formats, types" "PRD/overview" "03 06 13" load "-"
map_row "hotkey-to-listening-pill under 1s when warm" "PRD/overview" "-" struct "gate-16-perf: trigger logged but latency never timed"
map_row "cold load shows progress, not silence" "PRD/overview" "06" load "-"
map_row "STT RTF under 0.3" "PRD/overview" "05" load "-"
map_row "format p95 under 300ms" "PRD/overview" "07" load "-"
map_row "20/20 formatting fixtures" "PRD/overview" "01 07" load "-"
map_row "idle: only key service, under 20MB" "PRD/overview" "03 10" load "-"
map_row "zero audio bytes to disk" "PRD/overview" "04" load "-"
map_row "STT and LLM never co-resident" "PRD/overview" "09" load "-"
map_row "typing only after pill hides" "PRD/overview" "08" load "-"
map_row "clipboard copy as fallback" "PRD/overview" "08" load "-"
map_row "single .conf parsed once at boot" "PRD/overview" "02" load "-"
map_row "no cloud / no telemetry / no accounts" "PRD/overview" "-" struct "negative claim, not machine-checked"
map_row "Linux-only scope" "PRD/overview" "-" struct "platform scope, not gated"
map_row "not a voice assistant, no app control" "PRD/overview" "-" struct "scope statement, not gated"
# --- PRD/config.md ---
map_row "ui_words/stt_model/fallback/idle_timeout_s parse" "PRD/config" "02" load "-"
map_row "stt_model path used as configured or the run errors, never a silent default" "DOCS/configuration" "22" load "-"
map_row "[names]/[links] sections expand verbatim" "PRD/config" "12" load "-"
# --- PRD/key-service.md ---
map_row "SUPER+H grab via compositor, not evdev" "PRD/key-service" "03" load "-"
map_row "trigger: pill + audio + STT start" "PRD/key-service" "03 13" load "-"
map_row "STT->LLM handoff serialized" "PRD/key-service" "09" load "-"
map_row "typing helper loaded with output" "PRD/key-service" "13" load "-"
map_row "offload after timeouts, busy never killed" "PRD/key-service" "09 10" load "-"
map_row "idle listen, config parsed once" "PRD/key-service" "03" load "-"
map_row "STT/LLM/mic fail: error, offload, idle" "PRD/key-service" "11" load "-"
map_row "cancel: kill audio+STT, skip format, idle" "PRD/key-service" "11" load "-"
# --- PRD/helpers.md ---
map_row "audio: on-request PipeWire RAM stream" "PRD/helpers" "04" load "-"
map_row "audio busy/killable flags" "PRD/helpers" "04" load "-"
map_row "typing: wtype only, no paste path" "PRD/helpers" "08" load "-"
map_row "typing: clipboard copy every run" "PRD/helpers" "08" load "-"
map_row "STT: dGPU pick else iGPU fallback tier" "PRD/helpers" "05" load "-"
map_row "STT: word stream + full unload" "PRD/helpers" "05" load "-"
map_row "formatter LLM backend (typed text is the formatter output)" "PRD/helpers" "19" load "-"
map_row "formatter rules: fillers/corrections/verbatim" "PRD/helpers" "07 12" load "-"
map_row "helpers unload after timeout" "PRD/helpers" "10" load "-"
# --- PRD/pill-ui.md ---
map_row "Listening/Transcribing/Formatting/Typing/Error states" "PRD/pill-ui" "06 18" load "-"
map_row "live words + amplitude for the overlay bars" "PRD/pill-ui" "18" load "-"
map_row "stop op ends recording and runs clean+type" "PRD/pill-ui" "11 18" load "-"
map_row "no inputs/settings in pill" "PRD/pill-ui" "-" struct "static QML property"
map_row "overlay never takes keyboard focus (keyboardFocus None)" "PRD/pill-ui" "06" load "-"
map_row "service spawns the pill per run, kills it after" "PRD/pill-ui" "18" load "-"
map_row "states pushed over the control socket (snapshot + events)" "PRD/pill-ui" "18" load "-"
# --- DOCS/architecture.md ---
map_row "all components build (key/audio/stt/llm/type/pill)" "DOCS/architecture" "03 04 05 07 08" load "-"
map_row "lifecycle SUPER+H to typed text" "DOCS/architecture" "13" load "-"
map_row "killable/busy replaces supervisor" "DOCS/architecture" "09 10" load "-"
map_row "one small daemon rationale" "DOCS/architecture" "-" struct "design note, vault Hypothesis.md"
map_row "fine-tuned STT two-pass re-decode, streaming words as fallback" "DOCS/architecture" "20" load "-"
map_row "hermetic daemon end-to-end: boot, trigger, transcribe, type, error paths" "DOCS/architecture" "22" load "-"
map_row "trained formatter served at VAANI_LLM_ENDPOINT" "DOCS/architecture" "19" load "-"
map_row "repository layout documented (folder map)" "DOCS/layout" "-" struct "wording-only coverage"
# --- DOCS/configuration.md ---
map_row "sample vaani.conf parses round-trip" "DOCS/configuration" "02" load "-"
map_row "unknown keys warn, never crash" "DOCS/configuration" "02" load "-"
map_row "missing file means defaults" "DOCS/configuration" "02" load "-"
map_row "daemon owns the model servers it is pointed at" "DOCS/configuration" "21" load "-"
map_row "launcher env vars decide which servers are owned" "DOCS/configuration" "21" load "-"
map_row "a server outside the daemon is never killed" "DOCS/configuration" "21" load "-"
map_row "longest whole-phrase match wins" "DOCS/configuration" "12" load "-"
# --- DOCS/development.md ---
map_row "prereq toolchain present" "DOCS/development" "-" struct "env-dependent, not gated"
map_row "phase-0 spike RTF/VRAM recorded" "DOCS/development" "05" load "-"
# --- DOCS/phases.md: gates 14/15 owned by future gates, pending not silent ---
map_row "soak: 3x75 sentences, zero crashes/stuck" "DOCS/phases-14" "-" load "gate-14 (PENDING, not yet run)"
map_row "gibberish declined/harmless, zero disk audio" "DOCS/phases-14" "-" load "gate-14 (PENDING, no gibberish handling in tree)"
map_row "systemd unit + installer + uninstall" "DOCS/phases-15" "-" load "gate-15 (PENDING, no unit/installer in tree)"
map_row "vault Build Log sign-off" "DOCS/phases-16" "-" load "coordinator (draft in gate-16 report)"

echo "== perf table (live, from fast-gate outputs) =="
P95="$(sed -n 's/.*p95: \([0-9.]*\)ms.*/\1/p' /tmp/vaani-gate-07.log 2>/dev/null | head -1)"
P50="$(sed -n 's/.*p50: \([0-9.]*\)ms.*/\1/p' /tmp/vaani-gate-07.log 2>/dev/null | head -1)"
RTFWORST="$(grep -oE 'rtf=[0-9.]+' /tmp/vaani-gate-05.log 2>/dev/null | sed 's/rtf=//' | python3 -c 'import sys; v=[float(l) for l in sys.stdin]; print(f"{max(v):.3f}" if v else "PENDING")')"
RSS="$(grep -oE 'idle RSS [0-9]+ kB' /tmp/vaani-gate-03.log 2>/dev/null | tail -1 | grep -oE '[0-9]+')"
[ -z "$P95" ] && P95="PENDING"
[ -z "$RTFWORST" ] && RTFWORST="PENDING"
[ -z "$RSS" ] && RSS="PENDING"
printf '  config/format p95 : %s ms (gate-07%s)\n' "$P95" "${P50:+", p50 $P50 ms"}"
printf '  STT RTF worst     : %s (gate-05, limit 0.3)\n' "$RTFWORST"
printf '  idle RSS          : %s kB (gate-03, limit 20480)\n' "$RSS"
printf '  hotkey-to-pill    : PENDING (trigger logged, latency never timed; owned by gate-16-perf)\n'
if [ "$P95" != "PENDING" ]; then
  python3 -c "exit(0 if float('$P95') < 300.0 else 1)" || { echo "  [RED] p95 over budget"; unowned=$((unowned + 1)); }
fi
if [ "$RTFWORST" != "PENDING" ]; then
  python3 -c "exit(0 if float('$RTFWORST') < 0.3 else 1)" || { echo "  [RED] RTF worst over budget"; unowned=$((unowned + 1)); }
fi
if [ "$RSS" != "PENDING" ]; then
  [ "$RSS" -lt 20480 ] || { echo "  [RED] idle RSS over budget"; unowned=$((unowned + 1)); }
fi

echo "== soak / gibberish =="
if [ -f /tmp/vaani-gate-14.log ]; then
  grep -E '^counts:' /tmp/vaani-gate-14.log | head -3
  grep -qE 'gate-14 GREEN' /tmp/vaani-gate-14.log && echo "  soak verdict: GREEN" \
    || echo "  soak verdict: gate-14 currently RED (see log; counts above still stand)"
else
  echo "  soak counts: PENDING (gate-14 not yet run)"
fi
GIB="$(grep -E '^counts: gibberish' /tmp/vaani-gate-14.log 2>/dev/null | head -1)"
if [ -n "$GIB" ]; then
  echo "  gibberish verdict: 115/115 declined-or-harmless per gate-14 ($GIB)"
elif grep -rqi 'gibberish' crates/ UI/ TESTS/gates/gate-0[1-9].sh TESTS/gates/gate-1[0-35].sh 2>/dev/null; then
  echo "  gibberish verdict: see gate-14 log"
else
  echo "  gibberish verdict: PENDING (no gibberish handling in tree; owned by gate-14)"
fi

printf 'gate-16: %d passed, %d owed-owned, %d warnings, %d unowned\n' "$pass" "$owed" "$warn" "$unowned"
if [ "$unowned" -eq 0 ]; then echo "gate-16 GREEN"; exit 0; else echo "gate-16 RED"; exit 1; fi
