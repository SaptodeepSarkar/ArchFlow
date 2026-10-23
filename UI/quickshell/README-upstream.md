# ui — Quickshell "vaani" config (app-owned, NOT the desktop shell)

- `shell.qml`: event-driven overlay (Socket + SplitParser, snapshot-first,
  amplitude ≤30 Hz). Exits when idle. It is the whole config: no theme or
  component files, every colour is inline.

Install: `~/.config/quickshell/vaani/shell.qml`
(pkg: `/usr/share/quickshell/vaani/`). The overlay is launched on demand by
`vaani-key-service` and exits as soon as a run finishes.

The settings and onboarding views were removed: they drove a `vaanid.service`
and a config IPC that do not exist. Configuration lives in
`~/.config/vaani/vaani.conf`, read once at startup.
