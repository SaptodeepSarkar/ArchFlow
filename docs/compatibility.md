# Compatibility (tested versions only — blank = untested, copy-only)

| Client | Backend | Version tested | XWayland/native | Result |
|---|---|---|---|---|
| Hyprland focused app (generic) | clipboard + sendkey | Hyprland 0.56.2 | native | Paste requested (manual check pending) |
| Terminal (foot/kitty/alacritty) | copy-only | — | — | By policy, never auto-paste |
| Firefox text areas | — | untested | — | copy-only until tested |
| GTK/Qt editor | — | untested | — | copy-only until tested |
| VS Code | — | untested | — | copy-only until tested |
| GNOME / KDE / Sway | — | untested | — | copy-only + reason |

Capability probes (`vaani doctor`): pw-record, wl-copy, hyprctl, quickshell,
whisper-cli, curl, models present. Setup reports missing capabilities instead
of pretending success. `ydotool`/Fcitx5/portals: explicit optional future
adapters only — no invented universal D-Bus commit call.
