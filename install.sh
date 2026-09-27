#!/usr/bin/env bash
# Portable user installation. Only Vaani-owned files are installed.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.cargo/bin:$PATH"
with_trained_models=0
if [ "${1:-}" = "--with-trained-models" ]; then
  with_trained_models=1
elif [ -n "${1:-}" ]; then
  printf '%s\n' 'usage: ./install.sh [--with-trained-models]' >&2
  exit 2
fi
config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
data_root="${XDG_DATA_HOME:-$HOME/.local/share}"
bin_root="$HOME/.local/bin"
cargo build --locked --release --workspace
mkdir -p "$bin_root" "$config_root/systemd/user" "$config_root/hypr" "$config_root/vaani" "$data_root/applications" "$config_root/quickshell/vaani/assets" "$data_root/vaani"
for binary in vaanid vaani vaani-worker vaani-desktop; do
  install -m755 "target/release/$binary" "$bin_root/$binary"
done
install -m755 crates/vaani-worker/fw-transcribe.py "$bin_root/fw-transcribe.py"
install -m755 crates/vaani-worker/fw-server.py "$bin_root/fw-server.py"
install -m755 training/cleanup-llm/scripts/vaani_inject.py "$bin_root/vaani_inject.py"
install -m755 training/cleanup-llm/scripts/llm-server.py "$bin_root/llm-server.py"
python3 - "$bin_root/vaanid" "$config_root/systemd/user/vaanid.service" <<'PY'
import pathlib, sys
binary = sys.argv[1].replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
unit = pathlib.Path('packaging/vaanid.service').read_text().replace('/usr/bin/vaanid', '"' + binary + '"')
pathlib.Path(sys.argv[2]).write_text(unit)
PY
install -m644 packaging/hyprland/vaani.conf packaging/hyprland/vaani.lua "$config_root/hypr/"
python3 - "$bin_root/vaani-desktop" "$data_root/applications/vaani.desktop" <<'PY'
import pathlib, sys
binary = sys.argv[1].replace('\\', '\\\\').replace('"', '\\"')
entry = pathlib.Path('packaging/vaani.desktop').read_text().replace('vaani-desktop', '"' + binary + '"')
pathlib.Path(sys.argv[2]).write_text(entry)
PY
install -m644 ui/*.qml "$config_root/quickshell/vaani/"
install -m644 ui/assets/*.png "$config_root/quickshell/vaani/assets/"
install -m644 config.example.toml "$data_root/vaani/"
# Give a first install an editable, private config without replacing any
# existing choices on reinstall. The daemon also has this guard for package
# installs that do not use this script.
if [ ! -e "$config_root/vaani/config.toml" ]; then
  install -m600 config.example.toml "$config_root/vaani/config.toml"
fi
# Preserve an existing chosen shortcut when reinstalling, then regenerate the
# app-owned include and request a compositor reload. It never edits the user's
# main Hyprland configuration.
"$bin_root/vaani-desktop" shortcut
if [ "$with_trained_models" -eq 1 ]; then
  ./tools/install-trained-models.sh
fi
if ! command -v wtype >/dev/null 2>&1 && [ ! -x "$bin_root/wtype" ]; then
  printf '%s\n' 'NOTE: wtype not found — automatic paste falls back to Hyprland send_shortcut, which some native Wayland apps ignore.' 'For dependable injection: pacman -S wtype (official repo, no sudo performed here).'
fi
systemctl --user daemon-reload || true
systemctl --user try-restart vaanid.service || true
printf '%s\n' 'Installed Vaani. Caelestia is optional.' 'Next: add ~/.local/bin to PATH, run ./tools/setup-stt.sh, then:' '  systemctl --user enable --now vaanid.service' '  vaani doctor' 'See README.md for compositor shortcuts and system package installation.'
