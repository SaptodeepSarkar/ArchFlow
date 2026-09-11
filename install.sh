#!/usr/bin/env bash
# Portable user installation. Only Vaani-owned files are installed.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.cargo/bin:$PATH"
config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
data_root="${XDG_DATA_HOME:-$HOME/.local/share}"
bin_root="$HOME/.local/bin"
cargo build --locked --release --workspace
mkdir -p "$bin_root" "$config_root/systemd/user" "$config_root/hypr" "$data_root/applications" "$config_root/quickshell/vaani" "$data_root/vaani"
for binary in vaanid vaani vaani-worker; do
  install -m755 "target/release/$binary" "$bin_root/$binary"
done
python3 - "$bin_root/vaanid" "$config_root/systemd/user/vaanid.service" <<'PY'
import pathlib, sys
binary = sys.argv[1].replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
unit = pathlib.Path('packaging/vaanid.service').read_text().replace('/usr/bin/vaanid', '"' + binary + '"')
pathlib.Path(sys.argv[2]).write_text(unit)
PY
install -m644 packaging/hyprland/vaani.conf packaging/hyprland/vaani.lua "$config_root/hypr/"
install -m644 packaging/vaani.desktop "$data_root/applications/vaani.desktop"
install -m644 ui/*.qml "$config_root/quickshell/vaani/"
install -m644 config.example.toml "$data_root/vaani/"
systemctl --user daemon-reload || true
printf '%s\n' 'Installed Vaani. Caelestia is optional.' 'Next: add ~/.local/bin to PATH, run ./tools/setup-stt.sh, then:' '  systemctl --user enable --now vaanid.service' '  vaani doctor' 'See README.md for compositor shortcuts and system package installation.'
