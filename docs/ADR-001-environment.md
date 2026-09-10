# ADR-001 — Environment, stack verification, limitations

Date: 2026-09-10. Machine: the target laptop itself (NOT a remote container).

## Verified versions (measured, not assumed)

- Arch Linux rolling, kernel 7.2.3-arch1-2
- Hyprland 0.56.2 (abi efb5099…, hyprgraphics 0.5.1, hyprutils 0.14.2, aquamarine 0.15.0)
- PipeWire 1.6.8 (server + pw-record client), default clock 48 kHz
- wl-clipboard 2.3.0
- Quickshell 0.3.1 (AUR -git build 0.3.1.r10.g2d3b3e9; official extra has 0.3.1-1)
- Qt 6 via qmake6, systemd 261, NVIDIA 610.57 / CUDA UMD 13.3, RTX 3050 6 GB
- Rust stable 1.98.1 (user-local rustup; no sudo available in this env)
- whisper.cpp / CUDA toolkit: NOT installed — worker runs cpu-stub until pinned build exists

## Decisions

1. **Capture via `pw-record` subprocess**, not libpipewire-rs bindings:
   maintained PipeWire client, honours existing graph, no global changes.
   20 ms f32 blocks, bounded 120 s channel, drop-on-full backpressure.
2. **Worker one-shot over inherited stdin pipe** (framed binary audio without
   a TCP server or temp WAVs in the production path).
3. **Quickshell 0.3.1 API**: `PanelWindow` + `WlrLayershell.*` attached props
   (verified in installed caelestia-shell sources), `Quickshell.Io.Socket` +
   `SplitParser` (verified in installed qmltypes). NOT the 0.2.0 doc URLs
   verbatim — adapted to the installed release.
4. **Insertion = clipboard offer + `hyprctl dispatch sendkey`**; report
   "Paste requested", never "Inserted successfully". Terminals copy-only.
5. **Economy first**: worker exits per operation; Balanced/Ready accepted in
   config but currently prefetch-only (documented roadmap, not disguised).

## Limitations (honest)

- No whisper model downloaded here (network + size); transcription accuracy
  unmeasured — fixtures + wer.py provided, results pending user setup.
- Hold-to-talk release semantics depend on compositor bindr support; toggle
  is the dependable path until release matching is tested on this box.
- GNOME/KDE/Sway/XWayland insertion: copy-only, untested — listed separately.
- VRAM/idle numbers: budgets + harness provided; laptop measurements pending
  model download (never report container numbers as laptop numbers).
