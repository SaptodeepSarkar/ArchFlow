# PRD — Helpers (Rust)

## Audio helper (low level)

1. Opens a stream from the default mic via PipeWire on request only; never runs at boot.
2. Stream lives in RAM and is shared only with Vaani processes; zero bytes written to disk.
3. Exposes busy while recording, killable after stop + timeout.

## Typing helper (low level)

1. Types given text with `wtype`. Never uses paste injection.
2. Always copies the formatted output to clipboard as well (fallback if focus lands wrong).
3. Typing starts only after the pill hides, so keystrokes land in the previously focused window.

## STT manager (Rust, not low level)

1. Picks device on first run: dGPU if available, else iGPU (model tier drops accordingly).
2. Loads model into GPU memory on demand; streams words to the pill UI.
3. Default: faster-whisper `small.en` (CTranslate2 int8); fallback `base.en` on weak hardware.
4. Unloads fully before the formatter loads (VRAM serialization). Holds killable/busy state + idle timeout.

## LLM formatter (same process model as STT manager)

1. Default: Qwen2.5-1.5B-Instruct Q4 (proven on this machine class for harder JSON work).
2. Input: raw STT transcript. Output: formatted plain text only, no commentary.
3. Rules: strip fillers, drop self-corrected sentences (keep the correction), expand user-defined names/places/links verbatim.
4. Unloads after timeout like every other helper.
