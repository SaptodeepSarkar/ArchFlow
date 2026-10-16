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

The pill must hide before typing starts so keystrokes reach the previously focused window. Clipboard copy covers the case where focus still lands wrong.
