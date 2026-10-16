# PRD — Key Service (Rust, resident)

The only always-on process. Owns the hotkey, the config, and the lifecycle of every helper. Target footprint under 20MB idle.

## Responsibilities

1. Grab SUPER+H globally (via the compositor binding, not raw evdev, to avoid Hyprland conflicts).
2. On trigger: show the pill UI, start audio helper, load STT.
3. Manage STT → LLM handoff: unload STT, load formatter, feed raw transcript.
4. Load the typing helper with formatted output.
5. Offload pill, STT, LLM, typing helper after their timeouts; helpers reporting busy are never killed mid-work.
6. Return to idle listen. Parse `.conf` once at boot into variables.

## Kill-state model

Every helper exposes killable/busy. The key service polls state before offloading:

- `busy` (recording, inferring, typing): must not be killed; re-check after timeout.
- `killable` (done, timed out): offload immediately.

No separate supervisor: this model is the whole concurrency design.

## Failure handling

- STT or LLM fails to load: pill shows error state, key service offloads everything, returns to idle. Never leave a helper half-loaded.
- Audio stream fails: abort before STT load, show error, idle.
- Cancel button: kill audio + STT immediately, skip formatting, offload, idle.
