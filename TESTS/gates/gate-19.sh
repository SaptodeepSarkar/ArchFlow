#!/usr/bin/env bash
# Gate 19 — formatter pipeline (raw STT -> formatter LLM -> typed text).
#
# The contract: the daemon always calls the pipeline; with a reachable local
# LLM it uses the model, without one the deterministic rule engine answers.
# Tests:
#   1. fallback is deterministic when the endpoint is dead (always run),
#   2. the daemon's LLM path removes fillers and expands configured names
#      (runs when a server answers; reported as OWED otherwise, or failed
#      when VAANI_LLM_REQUIRED=1 asks for it to be enforced).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0; owed=0
ok()   { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }
owed() { printf '  [OWED] %s\n' "$1"; owed=$((owed + 1)); }

BIN="$ROOT/target/debug/vaani-key-service"
[ -x "$BIN" ] || { bad "daemon binary missing (build first)"; printf 'gate-19: %d passed, %d failed\n' "$pass" "$fail"; echo "gate-19 RED"; exit 1; }

TMP="$(mktemp -d /tmp/vaani-gate19.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT
cat >"$TMP/vaani.conf" <<'EOF'
hotkey = SUPER+H
ui_words = 4
idle_timeout_s = 120

[names]
saptodeep = Saptodeep Sarkar
EOF

# 1. no LLM: the rule engine must answer, deterministically.
FALLBACK="$(VAANI_LLM_ENDPOINT=http://127.0.0.1:1 "$BIN" --format-test \
  "umm send it to saptodeep hmm please" "$TMP/vaani.conf" 2>/dev/null | tail -1)"
if printf '%s' "$FALLBACK" | grep -q '^FORMAT-TEST backend=rules '; then
  ok "dead endpoint falls back to the rule engine"
else
  bad "dead endpoint falls back to the rule engine (got: $FALLBACK)"
fi
if [ "$FALLBACK" = "FORMAT-TEST backend=rules text=Send it to Saptodeep Sarkar please." ]; then
  ok "fallback output is deterministic and formatted"
else
  bad "fallback output (got: $FALLBACK)"
fi

# 2. live model, properties only: a generative formatter cannot be pinned to
# an exact string, so assert what the PRD actually promises.
ENDPOINT="${VAANI_LLM_ENDPOINT:-http://127.0.0.1:8081}"
LIVE="$(VAANI_LLM_ENDPOINT="$ENDPOINT" "$BIN" --format-test \
  "umm send it to saptodeep hmm please" "$TMP/vaani.conf" 2>/dev/null | tail -1)"
if printf '%s' "$LIVE" | grep -q 'backend=llm'; then
  TEXT="${LIVE#*text=}"
  if printf '%s' "$TEXT" | grep -qiE '\b(umm|hmm|uh|er)\b'; then
    bad "LLM output still carries fillers: $TEXT"
  else
    ok "LLM removed fillers"
  fi
  if printf '%s' "$TEXT" | grep -q 'Saptodeep Sarkar'; then
    ok "LLM expanded the configured name"
  else
    bad "LLM did not expand the configured name (got: $TEXT)"
  fi
  if printf '%s' "$TEXT" | grep -qiE '^(here is|sure|as an ai|i cannot)'; then
    bad "LLM answered with commentary: $TEXT"
  else
    ok "LLM answered with the transcript, not commentary"
  fi
else
  if [ "${VAANI_LLM_REQUIRED:-0}" = "1" ]; then
    bad "no LLM answered at $ENDPOINT (VAANI_LLM_REQUIRED=1)"
  else
    owed "no LLM at $ENDPOINT — started one, or set VAANI_LLM_ENDPOINT/VAANI_LLM_REQUIRED=1"
  fi
fi

printf 'gate-19: %d passed, %d failed, %d owed\n' "$pass" "$fail" "$owed"
if [ "$fail" -eq 0 ]; then echo "gate-19 GREEN"; exit 0; else echo "gate-19 RED"; exit 1; fi
