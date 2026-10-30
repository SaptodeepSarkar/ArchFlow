# PRD — Pill UI (QML + QuickShell)

Bottom-center pill that slides in on SUPER+H. Look reference: `ui/` folder at https://github.com/SaptodeepSarkar/ArchFlow/tree/main/ui (adapt, keep the overall pill feel).

## States (exactly three + error)

- Listening — user is speaking; shows live words.
- Transcribing — models working after speech ends; shows progress, not silence.
- Writing — formatted text is being typed.
- Error — load fail / mic fail; auto-dismisses back to idle.

## Content rules

- Transcription shows a 4-word trailing window (configurable count).
- One cancel button; cancels immediately, no formatting pass.
- No text input fields, no settings in the pill; settings live in `.conf`.

## Focus rule (load-bearing)

The pill never takes keyboard focus (`Qt.WindowDoesNotAcceptFocus`) so both
wtype keystrokes and the clipboard target the window the user was in. The
service also kills the pill when the run ends.

## Hosting + state protocol

Overlay: the Quickshell config `vaani` from ArchFlow `ui/` (graphite card,
lime activity mark, uppercase state label, live words, Stop button).
The key service spawns `quickshell -n -c vaani` per run (~230 ms cold start,
so idle cost is zero); the overlay exits itself after the final state.

States are pushed over `$XDG_RUNTIME_DIR/vaani/control.sock` as
newline-delimited JSON: STARTING, RECORDING, TRANSCRIBING, CLEANING,
INSERTING, READY, IDLE, CANCELLED, ERROR, plus `provisional` events
carrying the live words and `amplitude` events carrying the mic level for the
bars. The overlay's only op is `stop` (cancel this run; nothing is typed).
Details in `UI/README.md`.
