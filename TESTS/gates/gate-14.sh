#!/usr/bin/env bash
# Gate 14 (soak): 3x75 scripted sentences through format+type with zero
# crashes and zero stuck states, 15 curated + 100 seeded gibberish inputs all
# declined-or-harmless, and zero new audio bytes on disk across the soak.
# GREEN only if all of that holds. Uses stub wtype on PATH (exec-edge stub
# only, same as gate-13); the real wtype never fires.
#
# NOTE: a 10-minute live-mic soak is out of scope for this gate — there is no
# live mic in this harness. The loops below reuse TESTS/drivers/run_loop.sh
# --raw, i.e. the accelerated path through the same llm-format + type-text
# stages, which is the scripted soak Phase 14 asks for.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

LLM_FORMAT="${LLM_FORMAT:-$ROOT/target/debug/llm-format}"
TYPE_TEXT="${TYPE_TEXT:-$ROOT/target/debug/type-text}"
for b in "$LLM_FORMAT" "$TYPE_TEXT"; do
  [ -x "$b" ] || { echo "gate-14 RED: binary missing: $b (build first, gate does no rebuilds)"; exit 1; }
done

START="$SECONDS"
TMP="$(mktemp -d /tmp/vaani-gate14.XXXXXX)"
# Disk-audio marker BEFORE the soak (same dirs gate-04 watches).
MARKER="$(mktemp /tmp/vaani-gate14.marker.XXXXXX)"
sleep 1
touch "$MARKER"
trap 'rm -rf "$TMP" "$MARKER"' EXIT

# Stub wtype FIRST on PATH (exec-edge stubbing only); proven below.
mkdir -p "$TMP/shim"
cat >"$TMP/shim/wtype" <<'EOF'
#!/usr/bin/env bash
[ "$#" -eq 1 ] || { echo "stub wtype: expected 1 arg, got $#" >&2; exit 1; }
printf '%s' "$1" >"$VAANI_WTYPE_SCRATCH"
printf 'stub-fired bytes=%s\n' "${#1}" >>"$VAANI_WTYPE_LOG"
EOF
chmod +x "$TMP/shim/wtype"
export PATH="$TMP/shim:$PATH" VAANI_WTYPE_STUB="$TMP/shim/wtype" VAANI_WTYPE_LOG="$TMP/wtype.log"
export LLM_FORMAT TYPE_TEXT
: >"$VAANI_WTYPE_LOG"

# 1. scripted soak: 3 loops x 75 sentences + 115 gibberish via soak.py.
if python3 TESTS/drivers/soak.py --outdir "$TMP/soak" --summary "$TMP/summary.json" \
    >"$TMP/soak.out" 2>&1; then
  ok "soak driver ran to completion"
  cat "$TMP/soak.out"
else
  bad "soak driver ran to completion (see $TMP/soak.out)"
  cat "$TMP/soak.out"
fi

S="$(python3 -c "import json; print(open('$TMP/summary.json').read())" 2>/dev/null || true)"
if [ -z "$S" ]; then
  bad "soak summary written"
else
  ok "soak summary written"
  # shellcheck disable=SC2034
  eval "$(python3 - "$TMP/summary.json" <<'EOF'
import json, sys
s = json.load(open(sys.argv[1]))
sc, gb = s["scripted"], s["gibberish"]
for k in ("total", "ok", "crashes", "stuck", "mismatch"):
    print("SC_%s=%d" % (k.upper(), sc[k]))
for k in ("total", "declined", "harmless", "flagged", "crashes"):
    print("GB_%s=%d" % (k.upper(), gb[k]))
EOF
)"
fi

# 2. 225 sentences, 0 crashes, 0 stuck.
if [ "${SC_TOTAL:-0}" -eq 225 ] && [ "${SC_OK:-0}" -eq 225 ] \
    && [ "${SC_CRASHES:-1}" -eq 0 ] && [ "${SC_STUCK:-1}" -eq 0 ] \
    && [ "${SC_MISMATCH:-1}" -eq 0 ]; then
  ok "225/225 scripted sentences typed, 0 crashes, 0 stuck, 0 mismatches"
else
  bad "225 scripted sentences clean (total=${SC_TOTAL:-?} ok=${SC_OK:-?} crashes=${SC_CRASHES:-?} stuck=${SC_STUCK:-?} mismatch=${SC_MISMATCH:-?})"
fi

# 3. gibberish: 15 curated + 100 seeded, all declined or harmless.
if [ "${GB_TOTAL:-0}" -eq 115 ] \
    && [ "$(( ${GB_DECLINED:-0} + ${GB_HARMLESS:-0} ))" -eq 115 ] \
    && [ "${GB_FLAGGED:-1}" -eq 0 ] && [ "${GB_CRASHES:-1}" -eq 0 ]; then
  ok "115/115 gibberish declined-or-harmless (declined=${GB_DECLINED:-?} harmless=${GB_HARMLESS:-?})"
else
  bad "115 gibberish declined-or-harmless (total=${GB_TOTAL:-?} declined=${GB_DECLINED:-?} harmless=${GB_HARMLESS:-?} flagged=${GB_FLAGGED:-?} crashes=${GB_CRASHES:-?})"
fi

# 4. counts table.
printf -- '  ---- counts ----\n'
printf '  scripted : total=%s ok=%s crashes=%s stuck=%s\n' "${SC_TOTAL:-?}" "${SC_OK:-?}" "${SC_CRASHES:-?}" "${SC_STUCK:-?}"
printf '  gibberish: total=%s declined(noop)=%s harmless=%s flagged=%s crashes=%s\n' "${GB_TOTAL:-?}" "${GB_DECLINED:-?}" "${GB_HARMLESS:-?}" "${GB_FLAGGED:-?}" "${GB_CRASHES:-?}"
printf '  ok=%s noop=%s crashes=%s\n' "${SC_OK:-?}" "${GB_DECLINED:-?}" "$(( ${SC_CRASHES:-0} + ${GB_CRASHES:-0} ))"

# 5. stub proof: shim first on PATH, one stub firing per typed run
# (225 scripted + every harmless gibberish).
FIRED="$(grep -c '^stub-fired ' "$VAANI_WTYPE_LOG" 2>/dev/null || true)"
WANT_TYPED="$(( ${SC_OK:-0} + ${GB_HARMLESS:-0} ))"
if [ "$(command -v wtype)" = "$TMP/shim/wtype" ] && [ "${FIRED:-0}" -eq "$WANT_TYPED" ] \
    && [ "$WANT_TYPED" -ge 225 ]; then
  ok "stub wtype used for all $FIRED typings (real wtype never fired)"
else
  bad "stub wtype used (which wtype: $(command -v wtype); firings: ${FIRED:-0}, want $WANT_TYPED)"
fi

# 6. disk-audio audit across the whole soak (same dirs + expr as gate-04,
# except /tmp: it is shared with the whole desktop, so there we only flag
# names Vaani's own stack could produce. Our crates structurally write no
# audio files (see gate-04); this audit is the backstop, not the proof).
AUDIO_EXPR="\( -iname '*.wav' -o -iname '*.raw' -o -iname '*.pcm' -o -iname '*.au' -o -iname '*.snd' -o -iname '*.ogg' -o -iname '*.flac' \)"
NEW_AUDIO=""
for d in /dev/shm "$PWD" "$HOME/.cache"; do
  [ -d "$d" ] || continue
  FOUND="$(find "$d" -newer "$MARKER" -type f $AUDIO_EXPR 2>/dev/null)"
  [ -n "$FOUND" ] && NEW_AUDIO+="$FOUND "
done
if [ -d "${TMPDIR:-/tmp}" ]; then
  FOUND="$(find "${TMPDIR:-/tmp}" -maxdepth 1 -newer "$MARKER" -type f $AUDIO_EXPR \
    \( -iname 'vaani*' -o -iname '*vosk*' -o -iname '*transcribe*' -o -iname '*pw-record*' \) 2>/dev/null)"
  [ -n "$FOUND" ] && NEW_AUDIO+="$FOUND "
fi
if [ -z "$NEW_AUDIO" ]; then
  ok "disk-audio audit clean: zero new audio bytes across the soak"
else
  bad "disk-audio audit clean (new audio bytes: $NEW_AUDIO)"
fi

WALL="$(( SECONDS - START ))"
printf 'gate-14: %d passed, %d failed (wall %ds)\n' "$pass" "$fail" "$WALL"
if [ "$fail" -eq 0 ]; then echo "gate-14 GREEN"; exit 0; else echo "gate-14 RED"; exit 1; fi
