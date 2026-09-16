# Model inventory

Date: 2026-09-16

## Active runtime references

| Model/runtime | Location/reference | Status |
|---|---|---|
| whisper.cpp base | user-local `~/.local/share/vaani/models/base.bin`; `models/manifest.toml` | Current verified Linux STT path, weights not in Git |
| Cozy fine-tune | user-local CT2 directory referenced by `cozy` config/model resolution | Optional current fine-tuned path, weights not in Git |
| V5 Whisper CT2 | user-local `~/.local/share/vaani/models/v5-stt-whisper-v5-supervised-200-ct2/`; `recognition.model = "v5"` | Registered checksum-verified package; current host `doctor` reports it valid; no Android performance claim |
| V5 formatter experiments | `docs/V6_BASELINE.md`, training scripts, ignored local outputs | Evidence/control material, not a shipped runtime artifact |
| Android SpeechRecognizer | Android platform service | Current Android backend/fallback; on-device availability is device-dependent |

## Repository artifact result

`git ls-files` found no `.bin`, `.gguf`, `.safetensors`, `.pt`, `.onnx`, `.tflite`, or `.apk` model/build artifacts. Ignored local training outputs contain historical checkpoints, including V1–V5 experiments; they are not tracked and are not active product assets.

## Risks

- `models/manifest.toml` still has placeholder checksums for tiny/base.en/small.
- The runtime keeps legacy alias resolution, but package directories with a `model.json` sidecar now pass through schema, path, byte-size, and SHA-256 verification before inference. `recognition.model` and `recognition.live_model` reject unavailable or invalid artifacts before configuration is saved, preserving the prior in-memory selection. Valid packages are discoverable by manifest ID and the `doctor` response reports valid/invalid package entries.
- Android has no Vaani-owned STT package or model registry.

## Required next artifact

The V5 local package is now registered, checksum-validated, discoverable by ID, and selected through the `v5` alias without a UI-specific path. The remaining runtime gap is an Android-owned package/runtime; keep future V6/V7 registration data-driven.
