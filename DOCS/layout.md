# Repository layout

What lives where, and why. If you are looking for behaviour rather than
structure, `DOCS/architecture.md` is the one to read; this file is the map.

## Top level

| path | what it is |
|---|---|
| `crates/` | all Rust code, one directory per component (see below) |
| `install.sh` | the installer: builds if needed, installs binaries, config, overlay and the systemd user unit |
| `Cargo.toml`, `Cargo.lock` | workspace manifest and the pinned dependency graph |
| `README.md` | what Vaani is, how to run it, how the pieces fit |
| `DOCS/` | architecture, configuration, development, phase plan, this map |
| `PRD/` | the product requirements the gates are written against |
| `TESTS/` | the gate harness, its fixtures and drivers |
| `UI/` | the Quickshell pill overlay |
| `packaging/` | everything the daemon needs at runtime that is not Rust: the unit template, the trigger script, the model servers |
| `.github/workflows/` | CI on every push, and the tagged release pipeline |
| `.research/` | training and evaluation work: scripts, data, adapters, logs, the rendered report (gitignored; models ship as release assets) |
| `target/` | cargo's build output (gitignored) |

## `crates/` — one component per directory

Every crate is a library with the binary it owns in `src/bin/`, so the daemon
links logic instead of shelling out to itself.

| crate | library | binary | responsibility |
|---|---|---|---|
| `key-service/` | `main.rs`, `vad.rs`, `control.rs`, `cancel.rs`, `timeouts.rs` | `vaani-key-service` | the resident daemon: hotkey trigger, the record→decode→format→type loop, end-of-speech detection, the control socket the overlay speaks, cancellation and idle offload. Also the CLI test entries the gates drive (`--stream-test`, `--pipeline-test`, `--refine-test`, `--format-test`). |
| `audio-helper/` | `lib.rs` | `capture` | PipeWire microphone capture, on request, RAM-only: no audio ever reaches disk. |
| `stt-manager/` | `lib.rs` | `transcribe` | owns the STT backends: `Session` (batch), `LiveSession` (streaming), `transcribe_pcm` / `refine_pcm` (RAM PCM through a backend), and the `resolve_*` env lookups. `backend/` holds the python backends it spawns. |
| `llm-formatter/` | `lib.rs`, `llm.rs`, `vocab.rs` | `llm-format` | the formatter: an OpenAI-compatible HTTP client for the LLM path, the deterministic rule engine that answers when no model does, and vocabulary expansion. `tests/live_llm.rs` holds the `#[ignore]`d live tests. |
| `typing-helper/` | `lib.rs` | `type-text` | inserts the finished text with `wtype` and copies it to the clipboard. |
| `vaani-config/` | `lib.rs` | — | parses `~/.config/vaani/vaani.conf` once at boot, including the `[names]` / `[links]` vocabulary sections. |

`crates/stt-manager/backend/` is where the STT line protocol lives:

| file | role |
|---|---|
| `transcribe.py` | the streaming backend (Vosk): emits `W` words and `P` partials while the user speaks |
| `refine_whisper.py` | the re-decode client: posts the finished utterance to the fine-tuned model server and emits the same `W`/`DONE` lines |

## `packaging/` — runtime pieces that are not Rust

| path | what it is |
|---|---|
| `vaani-key.service` | the systemd **user** unit template. `# @BINDIR@` and `# @STT_ENV@` are replaced by `install.sh`, which is how the STT and model env vars reach the daemon. |
| `vaani-trigger` | the tiny script a static Hyprland keybind calls. It signals the daemon; Vaani never touches the compositor at runtime. |
| `serve-formatter.sh` | serves the formatter model (base GGUF + LoRA) with llama.cpp. Point `VAANI_LLM_ENDPOINT` at it. |
| `serve-refine-stt.sh` | starts the fine-tuned STT model server (wraps `serve-refine-stt.py` with the venv and adapter paths). Point `VAANI_STT_REFINE_ENDPOINT` at it. |
| (both `serve-*.sh` above) | the daemon can spawn and kill these itself when `VAANI_LLM_SERVER` / `VAANI_STT_REFINE_SERVER` name them -- see `DOCS/configuration.md`, "Model servers" |
| `serve-refine-stt.py` | the resident re-decode server: loads the fine-tuned Whisper once and answers `POST /transcribe` with raw PCM. |

## `TESTS/` — how "done" is proven

| path | what it is |
|---|---|
| `gate.sh` | the board: every gate status in one shot, and `gate.sh NN` to run one. |
| `gates/gate-NN.sh` | one script per phase, each asserting a contract and printing `gate-NN GREEN`/`RED`. |
| `ci.sh` | the hermetic subset that runs on GitHub runners (no mic, no GPU, no model servers), plus build and workspace tests. |
| `fixtures/` | the shared fixtures: formatting cases and the audio wavs (`fixtures/audio/`). |
| `drivers/` | helpers the gates use to drive the real system (`run_loop.sh`, `soak.py`, `pill_events.py`). |
| `test_fixtures.py` | the formatting-fixture contract test (gate 01). |

## `UI/` — the pill

`UI/quickshell/` is the overlay the daemon spawns per run: `shell.qml` plus the
theme, views and widgets it uses. `install.sh` copies it to
`~/.config/quickshell/vaani/`. `UI/README.md` explains the upstream Quickshell
bits it borrows.

## `.research/indic-stt-llm-training/` — the models, off to the side

Kept out of git (models and venvs are large) but kept in the tree, because the
scripts that produced the shipped models are as much a part of the project as
the models themselves.

| path | what it is |
|---|---|
| `scripts/` | training, export, evaluation and report scripts (STT training, formatter training, checkpoint sweeps, the endpoint comparison, `make_report.py`, `make_release_assets.py`) |
| `data/` | the name/company/place gazetteer used for biasing and for the casing evaluation |
| `out/` | run artifacts: adapters, logs, `report.html` (the rendered base-vs-trained report), benchmark JSON |
| `dist-v7/` | the assembled V7 release assets, uploaded to the GitHub release |
| `sources/`, `pdfs/` | the research the model choices rest on |
| `venv/` | the python environment with torch/transformers/peft used to train and to serve the re-decode model |
| `08-training-results.md` | the results of record, including the bugs found and the caveats |

## Where the models actually live

Models are **not** in the repository and not in `target/`. They are either
pulled from HuggingFace (the base Whisper and Qwen) or downloaded from the
GitHub release (`v7.0.0-models`: the two LoRA adapters), and the env vars in
`~/.local/vaani-stt.env` tell the daemon where to find them:

| variable | points at |
|---|---|
| `VAANI_STT_BACKEND` | the streaming backend script (installed to `~/.local/share/vaani/`) |
| `VAANI_STT_REFINE_BACKEND` | the re-decode client; its presence is what turns the second pass on |
| `VAANI_STT_REFINE_ENDPOINT` | the re-decode server (`serve-refine-stt.sh`) |
| `VAANI_LLM_ENDPOINT` | the formatter server (`serve-formatter.sh`) |
