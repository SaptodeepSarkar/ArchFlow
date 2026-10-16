#!/usr/bin/env bash
# Phase 08 gate (typing): wtype output byte-identical to input, clipboard
# matches, no alternate injection path in the crate. Typing is verified
# through an exec-edge stub wtype (records argv bytes to a scratch file);
# the real wtype binary must still be installed, and the clipboard roundtrip
# uses the real wl-copy/wl-paste. Exits 0 (GREEN) only if every check passes.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

pass=0; fail=0
ok()  { printf '  [GREEN] %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf '  [RED] %s\n' "$1"; fail=$((fail + 1)); }

CRATE="crates/typing-helper"
TMP="$(mktemp -d /tmp/vaani-gate08.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

# 1. real wtype present (stub below stands in only for the unobservable edge)
if command -v wtype >/dev/null; then
  ok "wtype present ($(command -v wtype))"
else
  bad "wtype not installed"
fi

# 2. clipboard tools present
if command -v wl-copy >/dev/null && command -v wl-paste >/dev/null; then
  ok "wl-copy/wl-paste present"
else
  bad "wl-copy/wl-paste not installed"
fi

# 3. crate builds + unit tests (pill-gate refusal needs no compositor)
if cargo build -p typing-helper >"$TMP/build.log" 2>&1; then
  ok "typing-helper builds"
else
  bad "typing-helper builds (see $TMP/build.log)"
fi
if cargo test -p typing-helper >"$TMP/test.log" 2>&1; then
  ok "cargo test -p typing-helper passes"
else
  bad "cargo test fails (see $TMP/test.log)"
fi
BIN="$ROOT/target/debug/type-text"
if [ -x "$BIN" ]; then
  ok "type-text binary built"
else
  bad "type-text binary missing at $BIN"
fi

# 4. no alternate injection path: forbidden tokens absent from crate sources
if grep -rniE 'paste|ydotool|xdotool|xclip|xsel|enigo|uinput|evdev' \
    "$CRATE/src" >"$TMP/forbidden.log" 2>&1; then
  bad "forbidden injection path in crate (see $TMP/forbidden.log)"
else
  ok "no alternate injection path in crate sources"
fi

# 5. only wtype + wl-copy are ever spawned by the crate
CMDS="$(grep -rhoE 'Command::new\("[^"]+"\)' "$CRATE/src" | sort -u)"
WANT="$(printf 'Command::new("wl-copy")\nCommand::new("wtype")')"
if [ "$CMDS" = "$WANT" ]; then
  ok "only wtype + wl-copy are spawned"
else
  bad "unexpected spawned commands: $(echo "$CMDS" | tr '\n' ' ')"
fi

# 6. exec-edge stub wtype: records the exact argv bytes to a scratch file
mkdir -p "$TMP/shim"
cat >"$TMP/shim/wtype" <<'EOF'
#!/usr/bin/env bash
# Test stub: record exactly what the helper asked to type.
[ "$#" -eq 1 ] || { echo "stub wtype: expected 1 arg, got $#" >&2; exit 1; }
printf '%s' "$1" >"$VAANI_WTYPE_SCRATCH"
EOF
chmod +x "$TMP/shim/wtype"
export VAANI_WTYPE_SCRATCH="$TMP/scratch"

run_case() { # $1=name $2=text
  rm -f "$VAANI_WTYPE_SCRATCH"
  printf '%s' "$2" >"$TMP/expected"
  if PATH="$TMP/shim:$PATH" "$BIN" --pill-hidden "$2" >"$TMP/run.log" 2>&1; then
    if [ -f "$VAANI_WTYPE_SCRATCH" ] \
      && cmp -s "$VAANI_WTYPE_SCRATCH" "$TMP/expected" \
      && wl-paste -n >"$TMP/clipboard" 2>/dev/null \
      && cmp -s "$TMP/clipboard" "$TMP/expected"; then
      ok "case $1: typed bytes identical, clipboard matches"
    else
      bad "case $1: typed/clipboard mismatch (see $TMP/run.log)"
    fi
  else
    bad "case $1: type-text exited nonzero (see $TMP/run.log)"
  fi
}

if [ -x "$BIN" ]; then
  run_case plain 'Hello world, this is Vaani.'
  run_case unicode-multiline "$(printf 'Line one.\nCaf\xc3\xa9 na\xc3\xafve \xe2\x80\x94 quoted & co. 123!')"
  run_case shell-hostile "$(printf 'Tabs\there, "quotes", $dollar `backtick` \\\\ slash!')"
fi

# 7. focus rule: without --pill-hidden nothing types and clipboard is untouched
if [ -x "$BIN" ]; then
  wl-paste -n >"$TMP/clip-before" 2>/dev/null || true
  rm -f "$VAANI_WTYPE_SCRATCH"
  if PATH="$TMP/shim:$PATH" "$BIN" 'Should never type.' \
      >"$TMP/norun.log" 2>&1; then
    bad "focus rule: type-text without --pill-hidden exited 0"
  elif [ -f "$VAANI_WTYPE_SCRATCH" ]; then
    bad "focus rule: keystrokes emitted while pill visible"
  elif ! wl-paste -n >"$TMP/clip-after" 2>/dev/null \
      || ! cmp -s "$TMP/clip-before" "$TMP/clip-after"; then
    bad "focus rule: clipboard touched while pill visible"
  else
    ok "focus rule: refused without --pill-hidden, no keys, clipboard intact"
  fi
fi

printf 'gate-08: %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then echo "gate-08 GREEN"; exit 0; else echo "gate-08 RED"; exit 1; fi
