# UI

The overlay is the Quickshell config `vaani` from ArchFlow `ui/` (verbatim in
`quickshell/`), installed to `~/.config/quickshell/vaani/`. Charcoal
`#17181C` card, lilac activity mark, uppercase state label, live words, Stop.

## Who runs it

The key service spawns `quickshell -n -c vaani` when a run starts. The
overlay exits by itself once the final state arrives (it lingers briefly so
the outcome stays readable); the service only waits, then kills a straggler.
`-n` means an instance you started by hand wins instead of a second window.

## Wire protocol (`$XDG_RUNTIME_DIR/vaani/control.sock`)

Newline-delimited JSON, both directions, implemented in
`crates/key-service/src/control.rs`.

Daemon → UI:

- first line of every connection, the **snapshot**: `{"protocol_version":1,
  "session_id":…,"state":…}` — the overlay quits at once if it is idle, so the
  daemon publishes STARTING *before* spawning the overlay.
- `{"event":"state","state":…,"message":…}` — STARTING, RECORDING,
  TRANSCRIBING, CLEANING, INSERTING, READY, IDLE, CANCELLED, ERROR.
- `…,"data":{"text":…,"copied":true}` on the final state: the text and whether
  it is on the clipboard (a clipboard confirmation lingers longer).
- `{"event":"provisional","data":{"tail":…,"words":…,"hidden":…}}` — live
  words; the overlay dims the context and highlights the newest word.
- `{"event":"amplitude","amplitude":0.0-1.0}` — mic level, one per audio chunk
  (~10 Hz) while recording, for the activity bars.

UI → daemon: `{"protocol_version":1,"request_id":…,"session_id":…,
"kind":{"op":"stop"}}`. `stop` cancels the current run: audio and STT stop, nothing is
formatted or typed.

## Focus rule

The overlay sets `WlrLayershell.keyboardFocus: None` and sits on the overlay
layer with `ExclusionMode.Ignore`. This is load-bearing: wtype and the
clipboard must target the window the user was in, not the overlay. It also
renders a pointer-blocking curtain during INSERTING so a stray click cannot
move focus mid-delivery.

## Not wired yet

`SettingsView.qml` / `OnboardingView.qml` ship with the config (the overlay
needs them to load) but the daemon has no config IPC for them yet: opening
settings (`VAANI_OPEN_SETTINGS=1`) shows the UI without live values.
