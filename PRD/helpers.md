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

1. Raw STT transcript in, formatted text out - per the working flow, the text
   that gets typed is the formatter's, never the raw STT.
2. Backend: any OpenAI-compatible chat endpoint on this machine
   (`VAANI_LLM_ENDPOINT`, default `http://127.0.0.1:8081`), e.g.
   Qwen2.5-1.5B-Instruct Q4 served by llama-server; ~90 ms warm on this box.
3. Prompt contract: strip fillers, keep the correction, fix capitalization and
   punctuation, expand the configured `[names]`/`[links]` pairs, and reply
   with ONLY the formatted text.
4. Deterministic rule engine answers when no endpoint is reachable, or when the
   model's reply fails a sanity check (empty, a preamble, or 3x the input):
   dictation must still work with no LLM around.
5. No commentary, ever - that sanity check is what keeps a model's musings out
   of the user's document.
