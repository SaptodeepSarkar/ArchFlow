# Vaani — Overview

## Goal

Press SUPER+H anywhere on a Linux desktop, speak, and have cleaned, formatted text typed at the cursor. All processing on-device.

## What it does

1. Global hotkey (SUPER+H) summons a pill UI and starts listening.
2. Local STT streams word-by-word transcription into the pill (4-word trailing window).
3. On finish, a local LLM formats the raw transcript: strips fillers ("umm", "hmm"), drops retracted sentences, expands custom names/places/links (say "Github", get `https://github.com/SaptodeepSarkar` typed).
4. The result is typed via `wtype` and copied to clipboard. Models offload after timeout; only the key service stays resident.

## Non-goals

- No cloud, no accounts, no telemetry. No disk recording of mic audio, ever.
- Linux only (PipeWire + Wayland + QuickShell). No Windows/macOS.
- Not a general voice assistant: no multi-step reasoning, no app control (that is Kyuma's job).

## Success criteria

- Hotkey to listening pill: under 1s after models warm; first cold load shows progress state, not silence.
- Transcription RTF under 0.3 on RTX 3050; formatting p95 under 300ms (same 1.5B class Kyuma validated).
- 20/20 formatting fixtures pass (`TESTS/fixtures/formatting.json`).
- Idle after timeout: only key service resident, target under 20MB; zero audio bytes written to disk.

## Constraints

- 6GB VRAM: STT and LLM are never co-resident; loads are serialized (STT unloads, formatter loads).
- Typing only after the pill hides (Wayland focus race); clipboard copy is the fallback.
- Config is a single `.conf` parsed once at boot (see `PRD/config.md`).
