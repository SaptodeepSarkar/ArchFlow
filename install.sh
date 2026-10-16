#!/usr/bin/env bash
# Vaani Phase 15 installer: dep check, build-if-needed, binaries to
# $PREFIX/bin (default ~/.local/bin), default vaani.conf (never overwritten),
# user unit install+enable, STT env discovery. Uninstall: ./install.sh --uninstall.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-$HOME/.local}"
BINDIR="$PREFIX/bin"
CONF_DIR="$HOME/.config/vaani"
CONF="$CONF_DIR/vaani.conf"
UNIT_DIR="${UNIT_DIR:-$HOME/.config/systemd/user}"
UNIT="$UNIT_DIR/vaani-key.service"
ENVFILE="$PREFIX/vaani-stt.env"
BINS="vaani-key-service capture transcribe llm-format type-text vaani-trigger"

die() { echo "install.sh: error: $1" >&2; exit 1; }
note() { echo "install.sh: $1"; }

if [ "${1:-}" = "--uninstall" ]; then
  if [ "$UNIT_DIR" = "$HOME/.config/systemd/user" ]; then
    systemctl --user disable vaani-key.service >/dev/null 2>&1 || true
  fi
  for b in $BINS; do rm -f "$BINDIR/$b"; done
  rm -f "$UNIT" "$ENVFILE"
  if [ "$UNIT_DIR" = "$HOME/.config/systemd/user" ]; then
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi
  note "removed binaries + unit; kept $CONF (delete by hand if really unwanted)"
  exit 0
fi

# 1. deps: hard fail on missing host tools; vosk python is a note (STT-only).
missing=""
for c in pw-record wtype quickshell python3; do
  command -v "$c" >/dev/null 2>&1 || missing="$missing $c"
done
[ -z "$missing" ] || die "missing deps:$missing (install them, then re-run)"
command -v systemd-analyze >/dev/null 2>&1 || note "warning: systemd-analyze absent, skipping unit verify"

# 2. binaries: reuse cargo output, else build (vaani-trigger is a script).
need_build=0
for b in $BINS; do
  [ "$b" = "vaani-trigger" ] && continue
  [ -x "$ROOT/target/release/$b" ] || need_build=1
done
if [ "$need_build" -eq 1 ]; then
  command -v cargo >/dev/null 2>&1 || die "no release binaries and no cargo to build them"
  (cd "$ROOT" && cargo build --release) || die "cargo build --release failed"
fi
for b in $BINS; do
  [ "$b" = "vaani-trigger" ] && continue
  [ -x "$ROOT/target/release/$b" ] || die "binary missing after build: $b"
done

# 3. STT discovery: env override wins, else Kyuma reuse, else warn-and-continue.
# shortcut: stt-manager still hardcodes Kyuma paths (src/lib.rs:18-21,
# backend/transcribe.py:54); these exports paper over it until that crate
# drops the hardcode. Owed fix, not fixed here (crates are out of scope).
KYPY="/home/saptodeep/Projects/Kyuma/.venv/bin/python"
KYMO="/home/saptodeep/Projects/Kyuma/models/vosk-model-small-en-us-0.15"
KYMF="/home/saptodeep/Projects/Kyuma/models/vosk-model-small-en-in-0.4"
py=""
if [ -n "${VAANI_STT_PYTHON:-}" ] && "$VAANI_STT_PYTHON" -c "import vosk" >/dev/null 2>&1; then
  py="$VAANI_STT_PYTHON"
elif [ -x "$KYPY" ] && "$KYPY" -c "import vosk" >/dev/null 2>&1; then
  py="$KYPY"
elif python3 -c "import vosk" >/dev/null 2>&1; then
  py="$(command -v python3)"
else
  note "warning: no python with vosk found (tried VAANI_STT_PYTHON, Kyuma venv, python3); STT will fail at runtime"
  py="$(command -v python3)"
fi
model=""
if [ -n "${VAANI_STT_MODEL:-}" ] && [ -d "$VAANI_STT_MODEL" ]; then
  model="$VAANI_STT_MODEL"
elif [ -d "$KYMO" ]; then
  model="$KYMO"
elif [ -d "$KYMF" ]; then
  model="$KYMF"
else
  note "warning: no STT model dir found (tried VAANI_STT_MODEL, Kyuma models); STT will fail at runtime"
fi

# 4. install binaries (vaani-trigger is a script, not a cargo artifact)
# + record STT env for shells and the gate.
mkdir -p "$BINDIR"
for b in $BINS; do
  if [ "$b" = "vaani-trigger" ]; then
    install -m755 "$ROOT/packaging/vaani-trigger" "$BINDIR/$b"
  else
    install -m755 "$ROOT/target/release/$b" "$BINDIR/$b"
  fi
done
{ echo "export VAANI_STT_PYTHON=\"$py\""; [ -n "$model" ] && echo "export VAANI_STT_MODEL=\"$model\""; } >"$ENVFILE"
note "binaries -> $BINDIR ; stt env -> $ENVFILE"

# 5. default config: never overwrite.
if [ -e "$CONF" ]; then
  note "keeping existing $CONF (not overwritten)"
else
  mkdir -p "$CONF_DIR"
  cat >"$CONF" <<'EOF'
# Vaani default config (see DOCS/configuration.md). Safe to edit.
hotkey = SUPER+H
ui_words = 4
stt_model = small.en
stt_fallback_model = base.en
llm_model = qwen2.5-1.5B-q4
prefer_device = auto
idle_timeout_s = 120

[names]
saptodeep = Saptodeep Sarkar

[links]
github = https://github.com/SaptodeepSarkar
EOF
  note "default config -> $CONF"
fi

# 5b. pill UI: the key service spawns `quickshell -c vaani` per run, so the
# config must exist. Never overwrite an existing one (user may have edited).
QS_DIR="$HOME/.config/quickshell/vaani"
mkdir -p "$QS_DIR"
if [ -e "$QS_DIR/shell.qml" ] && ! cmp -s "$ROOT/UI/quickshell/shell.qml" "$QS_DIR/shell.qml"; then
  cp "$QS_DIR/shell.qml" "$QS_DIR/shell.qml.bak-$(date +%Y%m%d%H%M)"
  note "backed up your modified shell.qml before installing the shipped one"
fi
for f in "$ROOT"/UI/quickshell/*.qml; do
  install -m644 "$f" "$QS_DIR/$(basename "$f")"
done
note "overlay config -> $QS_DIR ($(ls "$ROOT"/UI/quickshell/*.qml | wc -l) QML files)"

# 6. user unit: template ExecStart gets the real bindir, STT env spliced
# into [Service] (appending at EOF would land under [Install], where
# systemd silently ignores Environment=).
env_block="Environment=VAANI_STT_PYTHON=$py"
[ -n "$model" ] && env_block="$env_block
Environment=VAANI_STT_MODEL=$model"
tmp="$(mktemp)"
sed "s|@BINDIR@|$BINDIR|g" "$ROOT/packaging/vaani-key.service" \
  | awk -v e="$env_block" '{ if ($0 == "# @STT_ENV@") print e; else print }' >"$tmp"
mkdir -p "$UNIT_DIR"
install -m644 "$tmp" "$UNIT"
rm -f "$tmp"
if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "$UNIT" || note "warning: systemd-analyze verify flagged $UNIT"
fi
# Only talk to the user bus for real installs: a UNIT_DIR override means a
# hermetic/test prefix whose unit file the bus cannot see (enabling would
# silently act on whatever real unit shares the name).
if [ "$UNIT_DIR" = "$HOME/.config/systemd/user" ]; then
  if systemctl --user daemon-reload >/dev/null 2>&1 && systemctl --user enable vaani-key.service >/dev/null 2>&1; then
    note "unit enabled: $UNIT (starts at login; logs: journalctl --user -u vaani-key.service)"
  else
    note "warning: could not enable user unit (no user bus?); unit file is at $UNIT, enable by hand: systemctl --user enable vaani-key.service"
  fi
else
  note "test prefix: unit staged at $UNIT (bus left alone)"
fi
note "done. uninstall: ./install.sh --uninstall (keeps $CONF)"
cat <<EOF

Next (one-time): add the SUPER+H bind to your hyprland.lua.
  Vaani never binds keys at runtime: hyprctl eval + :remove() on Hyprland
  0.56.2 frees same-key binds by signature and leaves Lua handles dangling,
  which crashes the whole compositor (upstream bug, no released fix yet).
  Use the static bind instead:

    hl.bind("SUPER + H", hl.dsp.exec_cmd("$BINDIR/vaani-trigger"))

  Then: systemctl --user enable --now vaani-key.service
  The pill needs the UI config at $QS_DIR/shell.qml (installed above).
EOF
