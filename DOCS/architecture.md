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
3. User finishes: audio stops, STT unloads, the formatter (already preloaded at
   step 2) formats the raw transcript.
4. Formatted text out (CLEANING then INSERTING): typing helper types key by key, copies to clipboard, plays a done cue; overlay reports READY.
5. Timeouts: each helper offloads when killable; key service returns to idle.

The formatter preloads while speech streams, so its cold start never sits
between the last word and the typed text, and both models stay warm for
`idle_timeout_s` so a repeat dictation pays no load. Only the formatter's
inference waits for STT to unload. Helpers reporting busy are never killed.

Cancel is honored at every phase: mid-listen, while the streaming backend flushes
its final words (`LiveSession::finish` polls the stop flag every 50 ms and kills
the backend), and during the fine-tuned re-decode. Nothing is formatted or typed
after a Cancel.

## Why this shape

The resident set is one small daemon because model loads are the slow, heavy part and must be demand-driven on a 6GB GPU. Killable/busy replaces a supervisor. Decisions and measured numbers: vault `Projects/Vaani/Hypothesis.md`.

## Fine-tuned models (opt-in, both reversible)

Two trained models can be wired into this same pipeline. Each is opt-in and each
degrades to the previous behaviour, so a box without them runs exactly as before.

**Two-pass STT.** The streaming model keeps emitting words while the user speaks
(RTF ~0.09 for Vosk; a CTranslate2 Whisper `stt_model` streams by re-decoding
the last few seconds, and is what this box runs — see
`DOCS/configuration.md`). When `VAANI_STT_REFINE_BACKEND` names the
re-decode client and a model server answers on `VAANI_STT_REFINE_ENDPOINT`, the
finished utterance is re-transcribed by the fine-tuned Whisper and *those* words
are what get formatted and typed. The streaming words remain the fallback for
every failure mode — no backend configured, server unreachable, empty answer,
or the client-side deadline (`VAANI_STT_REFINE_DEADLINE`, 20 s, shorter than the
backend's own 120 s guard) — so a missing model can never lose what was said.
The wait is also cancellable: `refine_pcm_with` takes a cancel check while the
re-decode runs, so the daemon can end the pass on Cancel instead of waiting it
out. Server: `packaging/serve-refine-stt.sh`; client:
`crates/stt-manager/backend/refine_whisper.py`; covered by gate 20.

**Trained formatter.** No code change and no new interface: point
`VAANI_LLM_ENDPOINT` at the server `packaging/serve-formatter.sh` starts (the
base GGUF plus the LoRA adapter the training run produced) instead of the
untuned model. The deterministic rule engine stays the fallback; covered by
gate 19.

Measured base-vs-trained numbers, the checkpoint sweep, and the caveats behind
them live in `.research/indic-stt-llm-training/08-training-results.md` and its
rendered report.
