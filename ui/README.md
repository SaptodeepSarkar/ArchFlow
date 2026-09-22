# ui — Quickshell "vaani" config (app-owned, NOT the desktop shell)

- `shell.qml`: event-driven overlay (Socket + SplitParser, snapshot-first,
  amplitude ≤30 Hz) + settings FloatingWindow host. Exits when idle.
- `OnboardingView.qml`: the Android-matched four-screen first-run story,
  using the same local editorial artwork and native Vaani lockup.
- `SettingsView.qml`: brand-aligned Home, Personalize, Settings, and Account
  pages, including start/stop and start-at-login controls for `vaanid`.

Install: `~/.config/quickshell/vaani/{shell.qml,SettingsView.qml}`
(pkg: `/usr/share/quickshell/vaani/`). The overlay is launched on demand by
`vaanid`; the settings window is launched independently so it remains open
while the service is stopped and restarted.

The intro uses entrance motion plus Android-inspired language and writing-place
rails. Set `VAANI_REDUCE_MOTION=1` before launching the desktop app to keep
the same screens static.

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
