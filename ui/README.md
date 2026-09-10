# ui — Quickshell "vaani" config (app-owned, NOT the desktop shell)

- `shell.qml`: event-driven overlay (Socket + SplitParser, snapshot-first,
  amplitude ≤30 Hz) + settings FloatingWindow host. Exits when idle.
- `SettingsView.qml`: 5 pages over `config_get`/`config_set` IPC + one-shot
  mic-test/doctor requests. No polling loops.

Install: `~/.config/quickshell/vaani/{shell.qml,SettingsView.qml}`
(pkg: `/usr/share/quickshell/vaani/`). Launched on demand by vaanid:
overlay on STARTING, settings on `vaani settings` (VAANI_OPEN_SETTINGS=1).

Verified against installed Quickshell 0.3.1: PanelWindow +
WlrLayershell.exclusionMode/layer/keyboardFocus=None (no focus steal),
Socket/SplitParser IPC. Colours: charcoal #17181D, lavender #B9A3FF.
