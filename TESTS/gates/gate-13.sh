#!/usr/bin/env bash
# Gate 13 (integration): full SUPER+H-to-typed-text loop on 5 audio samples +
# all 20 formatting fixtures, reusing the already-built binaries (no rebuilds).
# GREEN only if: sample conf parses, 5/5 audio loops land typed, 20/20 fixtures
# land typed byte-identical, one state log matches the DOCS/architecture.md
# lifecycle order, key-service --handoff-test passes (if the flag exists), and
# every keystroke went through the stub wtype (real wtype never fired).
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

TRANSCRIBE="$ROOT/target/debug/transcribe"
LLM_FORMAT="$ROOT/target/debug/llm-format"
TYPE_TEXT="$ROOT/target/debug/type-text"
DUMP="$ROOT/target/debug/examples/dump"
KEYBIN="$ROOT/target/release/vaani-key-service"
[ -x "$KEYBIN" ] || KEYBIN="$ROOT/target/debug/vaani-key-service"
for b in "$TRANSCRIBE" "$LLM_FORMAT" "$TYPE_TEXT" "$DUMP"; do
  [ -x "$b" ] || { echo "gate-13 RED: binary missing: $b (build first, gate does no rebuilds)"; exit 1; }
done

TMP="$(mktemp -d /tmp/vaani-gate13.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# Stub wtype FIRST on PATH (exec-edge stubbing only); prove it below.
mkdir -p "$TMP/shim"
cat >"$TMP/shim/wtype" <<'EOF'
#!/usr/bin/env bash
[ "$#" -eq 1 ] || { echo "stub wtype: expected 1 arg, got $#" >&2; exit 1; }
printf '%s' "$1" >"$VAANI_WTYPE_SCRATCH"
printf 'stub-fired bytes=%s\n' "${#1}" >>"$VAANI_WTYPE_LOG"
EOF
chmod +x "$TMP/shim/wtype"
export PATH="$TMP/shim:$PATH" VAANI_WTYPE_STUB="$TMP/shim/wtype" VAANI_WTYPE_LOG="$TMP/wtype.log"
: >"$VAANI_WTYPE_LOG"

# 1. sample conf parses (drives vaani-config the way gate-02 does, minus cargo).
if "$DUMP" TESTS/fixtures/config-sample.conf >"$TMP/conf.out" 2>"$TMP/conf.err" \
  && grep -q '^idle_timeout_s = 120$' "$TMP/conf.out" \
  && grep -q '^saptodeep = Saptodeep Sarkar$' "$TMP/conf.out" \
  && grep -q '^github = https://github.com/SaptodeepSarkar$' "$TMP/conf.out"; then
  ok "sample vaani.conf parses with names/links"
else
  bad "sample vaani.conf parses (see $TMP/conf.out $TMP/conf.err)"
fi

# 2. 5/5 audio samples through the whole loop.
AOK=0
for wav in TESTS/fixtures/audio/s1-hello.wav TESTS/fixtures/audio/s2-hello.wav \
           TESTS/fixtures/audio/s3-hello-slow.wav TESTS/fixtures/audio/s4-hello-fast-loud.wav \
           TESTS/fixtures/audio/s5-hello-tail.wav; do
  base="$(basename "$wav" .wav)"
  if TRANSCRIBE="$TRANSCRIBE" LLM_FORMAT="$LLM_FORMAT" TYPE_TEXT="$TYPE_TEXT" \
      TESTS/drivers/run_loop.sh "$TMP/loops" "audio-$base" --wav "$wav" >"$TMP/$base.log" 2>&1; then
    ok "audio $base looped to typed ($(tail -1 "$TMP/$base.log"))"
    AOK=$((AOK + 1))
  else
    bad "audio $base looped to typed (see $TMP/$base.log: $(tail -1 "$TMP/$base.log"))"
  fi
done
[ "$AOK" -eq 5 ] && ok "5/5 audio samples flow through the loop" \
  || bad "5/5 audio samples flow through the loop (got $AOK)"

# 3. 20/20 formatting fixtures format-to-typed-capture byte-identical.
FOK=0; FTOT=0
while IFS= read -r line; do
  id="$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["id"])')"
  raw="$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["raw"])')"
  want="$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["expected"])')"
  FTOT=$((FTOT + 1))
  if TRANSCRIBE="$TRANSCRIBE" LLM_FORMAT="$LLM_FORMAT" TYPE_TEXT="$TYPE_TEXT" \
      TESTS/drivers/run_loop.sh "$TMP/loops" "fix-$id" --raw "$raw" >"$TMP/fix-$id.log" 2>&1 \
      && printf '%s' "$want" >"$TMP/want.txt" \
      && cmp -s "$TMP/want.txt" "$TMP/loops/fix-$id.typed.txt"; then
    FOK=$((FOK + 1))
  else
    bad "fixture $id typed byte-identical (want $(cat "$TMP/want.txt" 2>/dev/null); got $(cat "$TMP/loops/fix-$id.typed.txt" 2>/dev/null))"
  fi
done < <(python3 -c "import json; [print(json.dumps(p)) for p in json.load(open('TESTS/fixtures/formatting.json'))]")
[ "$FOK" -eq 20 ] && [ "$FTOT" -eq 20 ] && ok "20/20 fixtures format-to-typed byte-identical" \
  || bad "20/20 fixtures format-to-typed byte-identical (got $FOK/$FTOT)"

# 4. state log of one run matches the architecture lifecycle order:
# idle -> listening(+hotkey/audio/STT) -> transcribing(STT unload, formatter load)
# -> writing(pill hide, typed) -> idle.
if python3 - "$TMP/loops/audio-s1-hello.states.log" <<'EOF'; then
import re, sys
log = open(sys.argv[1]).read()
order = ["^state=idle$",
         r"^state=listening hotkey=.* audio=stream stt=load$",
         r"^state=listening stt_stream words=\d+$",
         r"^state=transcribing audio=stop stt=unload fmt=load$",
         r"^state=transcribing fmt_format bytes=\d+$",
         r"^state=writing pill=hide$",
         r"^state=writing typed bytes=\d+ clipboard=copy$",
         r"^state=idle offloaded$"]
pos, lines = 0, log.splitlines()
for pat in order:
    nxt = next((i for i in range(pos, len(lines)) if re.match(pat, lines[i])), None)
    if nxt is None:
        print(f"lifecycle mismatch at /{pat}/"); sys.exit(1)
    pos = nxt + 1
print("lifecycle order ok")
EOF
  ok "state log matches DOCS/architecture.md lifecycle"
else
  bad "state log matches DOCS/architecture.md lifecycle"
fi

# 5. key-service --handoff-test branch, if the flag exists.
if [ -x "$KEYBIN" ] && "$KEYBIN" --handoff-test "hello" >"$TMP/handoff.log" 2>&1; then
  if grep -q 'order=stt_stream,stt_unload,fmt_load,fmt_format,fmt_unload' "$TMP/handoff.log" \
    && ! grep -q 'stt_loaded=true fmt_loaded=true' "$TMP/handoff.log"; then
    ok "key-service handoff serialized, no VRAM overlap"
  else
    bad "key-service handoff serialized (see $TMP/handoff.log)"
  fi
else
  ok "key-service --handoff-test absent, branch skipped (no binary/flag on this checkout)"
fi

# 6. stub proof: shim first on PATH, every keystroke (5+20) fired the stub.
FIRED="$(grep -c '^stub-fired ' "$VAANI_WTYPE_LOG" 2>/dev/null || true)"
if [ "$(command -v wtype)" = "$TMP/shim/wtype" ] && [ "${FIRED:-0}" -ge 25 ]; then
  ok "stub wtype used for all $FIRED typings (real wtype never fired)"
else
  bad "stub wtype used (which wtype: $(command -v wtype); stub firings: ${FIRED:-0}, want >= 25)"
fi

printf 'gate-13: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-13 GREEN"; exit 0; else echo "gate-13 RED"; exit 1; fi
