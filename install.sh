#!/usr/bin/env bash
# Dev install: binaries -> ~/.local/bin, user unit, hypr include, quickshell config.
# Touches ONLY vaani-owned paths. Never upgrades the system, never edits dotfiles.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.cargo/bin:$PATH"
cargo build --release
mkdir -p ~/.local/bin ~/.config/systemd/user ~/.config/hypr ~/.local/share/applications
install -m755 target/release/vaanid ~/.local/bin/vaanid
install -m755 target/release/vaani ~/.local/bin/vaani
install -m755 target/release/vaani-worker ~/.local/bin/vaani-worker
sed "s|%h|$HOME|" packaging/vaanid.service > ~/.config/systemd/user/vaanid.service
install -m644 packaging/hyprland/vaani.conf ~/.config/hypr/vaani.conf
install -m644 packaging/vaani.desktop ~/.local/share/applications/vaani.desktop
if [ -d ~/.config/quickshell ]; then
  mkdir -p ~/.config/quickshell/vaani
  install -m644 ui/shell.qml ~/.config/quickshell/vaani/shell.qml
  install -m644 ui/SettingsView.qml ~/.config/quickshell/vaani/SettingsView.qml
  echo "quickshell config installed to ~/.config/quickshell/vaani/"
else
  echo "NOTE: ~/.config/quickshell missing — UI files staged in ./ui/ (see docs/configuration.md)"
fi
systemctl --user daemon-reload || true
echo "OK. Next:"
echo "  1. add 'source = ~/.config/hypr/vaani.conf' to ~/.config/hypr/hyprland.conf"
echo "  2. systemctl --user enable --now vaanid.service"
echo "  3. vaani doctor && vaani settings"
