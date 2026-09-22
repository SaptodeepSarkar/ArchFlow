#!/usr/bin/env bash
# Remove the user-local Vaani installation created by install.sh.
# Personal config, personalization, models, and caches are intentionally kept.
set -euo pipefail

config_root="${XDG_CONFIG_HOME:-$HOME/.config}"
data_root="${XDG_DATA_HOME:-$HOME/.local/share}"
bin_root="$HOME/.local/bin"

systemctl --user disable --now vaanid.service 2>/dev/null || true
rm -f "$config_root/systemd/user/vaanid.service"
rm -f "$config_root/systemd/user/graphical-session.target.wants/vaanid.service"
systemctl --user daemon-reload 2>/dev/null || true

for file in \
  vaani vaanid vaani-worker vaani-desktop \
  whisper-cli whisper-cli-cuda vad-speech-segments \
  fw-transcribe.py fw-server.py vaani_inject.py llm-server.py; do
  rm -f "$bin_root/$file"
done
rm -f "$config_root/hypr/vaani.conf" "$config_root/hypr/vaani.lua"
rm -f "$data_root/applications/vaani.desktop"
rm -rf "$config_root/quickshell/vaani"

printf '%s\n' 'Removed Vaani binaries, service unit, launcher, Hyprland include, and Quickshell UI.'
printf '%s\n' 'Kept ~/.config/vaani, ~/.local/share/vaani, and caches so personal data/models are safe.'
