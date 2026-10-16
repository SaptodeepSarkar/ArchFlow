# PRD — Key Service (Rust, resident)

The only always-on process. Owns the hotkey, the config, and the lifecycle of every helper. Target footprint under 20MB idle.

## Responsibilities

1. Receive the SUPER+H trigger: a static bind in the user's `hyprland.lua` runs `vaani-trigger`, which signals this service (pid file + `SIGUSR1`). Vaani never binds or unbinds keys at runtime.
2. On trigger: start audio helper, load STT.
3. Manage STT → LLM handoff: unload STT, load formatter, feed raw transcript.
4. Load the typing helper with formatted output.
5. Offload pill, STT, LLM, typing helper after their timeouts; helpers reporting busy are never killed mid-work.
6. Return to idle listen. Parse `.conf` once at boot into variables.

## Why no runtime keybind registration

Hyprland 0.56.2's `removeKeybind` removes binds by signature (mod+key), not
identity: removing one of two same-key binds frees both objects and leaves
Lua holding a dangling pointer. The next time that handle is touched the
compositor SIGSEGVs. Upstream fixed it on git main (identity-based removal,
weak-pointer locking); no released package carries the fix. So the bind is
static config and this service only ever receives signals — there is no
handle that can dangle.

## Kill-state model

Every helper exposes killable/busy. The key service polls state before offloading:

- `busy` (recording, inferring, typing): must not be killed; re-check after timeout.
- `killable` (done, timed out): offload immediately.

No separate supervisor: this model is the whole concurrency design.

## Failure handling

- STT or LLM fails to load: pill shows error state, key service offloads everything, returns to idle. Never leave a helper half-loaded.
- Audio stream fails: abort before STT load, show error, idle.
- Cancel button: kill audio + STT immediately, skip formatting, offload, idle.
