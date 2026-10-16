#!/usr/bin/env bash
# Phase 13 driver: one SUPER+H-to-typed-text run through the EXISTING binaries.
# Usage:
#   run_loop.sh OUTDIR NAME --wav PATH     # audio sample entry
#   run_loop.sh OUTDIR NAME --raw "text"   # fixture-text entry
# Writes OUTDIR/NAME.{states.log,raw.txt,formatted.txt,typed.txt} and exits
# nonzero unless typed bytes are byte-identical to formatted output.
# The caller must put the stub wtype dir first on PATH and export
# VAANI_WTYPE_STUB=<stub path>; the driver refuses to run otherwise, so the
# real wtype can never fire inside the loop.
set -u
OUTDIR="$1"; NAME="$2"; MODE="$3"; SRC="$4"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TRANSCRIBE="${TRANSCRIBE:-$ROOT/target/debug/transcribe}"
LLM_FORMAT="${LLM_FORMAT:-$ROOT/target/debug/llm-format}"
TYPE_TEXT="${TYPE_TEXT:-$ROOT/target/debug/type-text}"
STUB="$(command -v wtype)"
[ "${VAANI_WTYPE_STUB:-}" = "$STUB" ] || {
  echo "run_loop $NAME: refusing, wtype resolves to '$STUB', not stub '${VAANI_WTYPE_STUB:-unset}'" >&2; exit 1; }
mkdir -p "$OUTDIR"
STATES="$OUTDIR/$NAME.states.log"; : >"$STATES"
say() { printf '%s\n' "$1" >>"$STATES"; }

say "state=idle"
case "$MODE" in
  --wav)
    say "state=listening hotkey=SUPER+H audio=stream stt=load"
    TOUT="$("$TRANSCRIBE" --wav "$SRC" 2>"$OUTDIR/$NAME.stt.err")" \
      || { echo "run_loop $NAME: transcribe failed" >&2; exit 1; }
    RAW="$(printf '%s\n' "$TOUT" | sed -n 's/^word .* text=//p' | paste -sd' ' -)"
    NWORDS="$(printf '%s\n' "$TOUT" | grep -c '^word ')"
    [ "$NWORDS" -ge 1 ] || { echo "run_loop $NAME: no words streamed" >&2; exit 1; }
    say "state=listening stt_stream words=$NWORDS"
    say "state=transcribing audio=stop stt=unload fmt=load"
    ;;
  --raw)
    RAW="$SRC"
    say "state=listening hotkey=SUPER+H audio=stream stt=load"
    say "state=listening stt_stream words=$(printf '%s' "$RAW" | wc -w | tr -d ' ')"
    say "state=transcribing audio=stop stt=unload fmt=load"
    ;;
  *) echo "run_loop: unknown mode $MODE" >&2; exit 2 ;;
esac
printf '%s' "$RAW" >"$OUTDIR/$NAME.raw.txt"
FMT="$(printf '%s\n' "$RAW" | "$LLM_FORMAT" 2>"$OUTDIR/$NAME.fmt.err")" \
  || { echo "run_loop $NAME: llm-format failed" >&2; exit 1; }
[ -n "$FMT" ] || { echo "run_loop $NAME: empty formatted text" >&2; exit 1; }
printf '%s' "$FMT" >"$OUTDIR/$NAME.formatted.txt"
say "state=transcribing fmt_format bytes=${#FMT}"
say "state=writing pill=hide"
export VAANI_WTYPE_SCRATCH="$OUTDIR/$NAME.scratch"
"$TYPE_TEXT" --pill-hidden "$FMT" >"$OUTDIR/$NAME.type.out" 2>&1 \
  || { echo "run_loop $NAME: type-text failed" >&2; cat "$OUTDIR/$NAME.type.out" >&2; exit 1; }
cp "$OUTDIR/$NAME.scratch" "$OUTDIR/$NAME.typed.txt"
say "state=writing typed bytes=$(wc -c <"$OUTDIR/$NAME.typed.txt" | tr -d ' ') clipboard=copy"
say "state=idle offloaded"
cmp -s "$OUTDIR/$NAME.formatted.txt" "$OUTDIR/$NAME.typed.txt" \
  || { echo "run_loop $NAME: typed != formatted" >&2; exit 1; }
echo "run_loop $NAME ok raw='$RAW' fmt='$FMT'"
