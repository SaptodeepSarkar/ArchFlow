# Architecture

## Components

- `key-service` (Rust, resident): config, lifecycle, pid file. Only idle process. Receives SUPER+H from a static `hyprland.lua` bind via `vaani-trigger`; it never registers keybinds at runtime (Hyprland 0.56.2 crashes on that — see PRD/key-service.md).
- `audio-helper` (Rust): PipeWire RAM stream, on demand.
- `stt-manager` (Rust): faster-whisper, streams words to UI.
- `llm-formatter` (Rust + llama.cpp): formats raw transcript.
- `typing-helper` (Rust): `wtype` + clipboard.
- `pill` (QML/QuickShell): 3 states + error, 4-word window, cancel.

## Lifecycle (SUPER+H to typed text)

1. Idle: key service listens. Nothing else loaded.
2. Hotkey: overlay shows (STARTING then RECORDING), audio streams, STT loads and streams live words over the control socket.
3. User finishes: audio stops, STT unloads, formatter loads, raw transcript in.
4. Formatted text out (CLEANING then INSERTING): typing helper types + clipboard copy, overlay reports READY.
5. Timeouts: each helper offloads when killable; key service returns to idle.

STT and formatter are never in VRAM together. Helpers reporting busy are never killed.

## Why this shape

The resident set is one small daemon because model loads are the slow, heavy part and must be demand-driven on a 6GB GPU. Killable/busy replaces a supervisor. Decisions and measured numbers: vault `Projects/Vaani/Hypothesis.md`.
