# ui — Quickshell "vaani" config (app-owned, NOT the desktop shell)

- `shell.qml`: event-driven overlay (Socket + SplitParser, snapshot-first,
  amplitude ≤30 Hz) + settings FloatingWindow host. Exits when idle.
- `OnboardingView.qml`: first-run Android-inspired setup for local mode,
  microphone, vocabulary, and residency profile. Account sync remains optional
  and is owned by the secure `vaani-desktop login` boundary.
- `SettingsView.qml`: 5 pages over `config_get`/`config_set` IPC + one-shot
  mic-test/doctor requests. No polling loops.

Install: `~/.config/quickshell/vaani/{shell.qml,SettingsView.qml}`
(pkg: `/usr/share/quickshell/vaani/`). Launched on demand by vaanid:
overlay on STARTING, settings on `vaani settings` (VAANI_OPEN_SETTINGS=1).

Verified against installed Quickshell 0.3.1: PanelWindow +
WlrLayershell.exclusionMode/layer/keyboardFocus=None (no focus steal),
Socket/SplitParser IPC. Colours: charcoal #17181D, lavender #B9A3FF.

The shared `Theme.qml` reads Caelestia colors optionally; copy all three QML
files when installing manually. No Caelestia QML modules are imported.
Settings receives an explicit controller bridge. The compact voice box renders
daemon-provided provisional STT words in its primary line; it does not predict,
clean, hold, or type transcript text. Its only action is `stop`; cleanup,
focus checks, clipboard delivery, and virtual-keyboard insertion stay in
`vaanid`/`inserter.rs`.
