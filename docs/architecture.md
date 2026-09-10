# Architecture

```
text field focused
      │  Super+Alt+Space (Hyprland bind -> `vaani toggle`, no /dev/input)
      ▼
┌──────────┐  unix sock   ┌──────────┐  spawn on demand  ┌──────────────┐
│  vaani   │─────────────▶│  vaanid  │──────────────────▶│ vaani-worker │
│  (CLI)   │◀─────────────│ (daemon) │──▶ pw-record ──▶ PCM pipe ──▶    │ (whisper)│
└──────────┘  snapshot+   │ state    │   (capture thread,│ JSON line    │
              events      │ machine  │    bounded queue) │ back         │
                          └────┬─────┘                   └──────────────┘
                               │ events (Socket+SplitParser, no polling)
                               ▼
                    ┌────────────────────┐
                    │ Quickshell "vaani" │ overlay (layer-shell, no kbd focus)
                    │ overlay + settings │ settings (FloatingWindow, focusable)
                    └────────────────────┘ exits when unneeded
```

- `crates/vaani-core`: config, versioned protocol, state machine, VAD, segment/reconcile.
- `crates/vaanid`: orchestration only — capture thread, focus checks
  (`hyprctl activewindow -j`), clipboard (`wl-copy`), key dispatch
  (`hyprctl dispatch sendkey`), worker supervision, pending-text expiry.
- `crates/vaani-cli`: thin structured IPC client.
- `crates/vaani-worker`: stdin PCM → stdout JSON; whisper-cli or silence-safe stub.
- States: IDLE→STARTING→RECORDING→TRANSCRIBING→CLEANING→READY→INSERTING→IDLE,
  with CANCELLED/ERROR exits. Only the controller transitions; stale results die.
- Control socket: `$XDG_RUNTIME_DIR/vaani/control.sock` (0700/0600), 1 MiB cap,
  protocol v1, request ids, subscriber snapshot-first.
- Privacy: no history by default, memory-only audio/text, logs carry state +
  timings only, 5-min pending expiry, lock/suspend cancels capture.
