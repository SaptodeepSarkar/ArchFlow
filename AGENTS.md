# AGENTS.md — working guide for AI agents on Vaani (repo: ArchFlow)

Read this before changing code. The spec is `arch-voice-flow-build-prompt.md`.
Environment truth lives in `docs/ADR-001-environment.md` — verify there, never assume.

## Project order (build slices map 1:1 to version commits)

| # | Slice | Paths | Commit |
|---|---|---|---|
| 1 | Workspace + core: protocol, state machine, config, VAD, segment/reconcile | `Cargo.toml`, `rust-toolchain.toml`, `.gitignore`, `crates/vaani-core/` | `v0.1.0 core` |
| 2 | Controller: orchestration, capture, focus, clipboard, insertion, cleanup, worker supervision | `crates/vaanid/` | `v0.1.0 daemon` |
| 3 | CLI + inference worker | `crates/vaani-cli/`, `crates/vaani-worker/` | `v0.1.0 cli+worker` |
| 4 | Quickshell overlay + settings (verified vs installed 0.3.1 API) | `ui/` | `v0.1.0 ui` |
| 5 | Systemd unit, desktop entry, PKGBUILD, Hyprland binds, model manifest, setup/bench tools, example config, installer | `packaging/`, `models/`, `tools/`, `native/worker/`, `config.example.toml`, `install.sh` | `v0.1.0 packaging` |
| 6 | Docs, fixtures, integration tests | `docs/`, `tests/`, `crates/*/tests/` | `v0.1.0 docs+tests` |
| 7 | Live-hardware fix: silence short-circuit `TRANSCRIBING → IDLE` + regression test | `crates/vaani-core/src/state.rs`, `tests/protocol_abuse.rs` | `v0.1.0 fix` |
| 8 | Meta: README, license, this file | `README.md`, `LICENSE-MIT`, `AGENTS.md` | `v0.1.0 meta` |

Tag `v0.1.0` = slice 8. Future versions: bump `Cargo.toml` workspace crates +
`packaging/PKGBUILD` `pkgver` together, one commit per version, annotated tag.

## Version history

- **v0.5.0** (2026-09-11): UI and distribution redesign. Compact two-word
  live preview, optional Caelestia dynamic colors with an independent fallback
  theme, redesigned settings navigation, system-wide Arch packaging, portable
  XDG-aware local install, and fixes from the published bug audit. One commit:
  `v0.5.0 ui+distribution`, tag `v0.5.0`.
- **v0.3.1** (2026-09-11): capture/insertion hardening. `pw-record --target`
  before positional output (was silently ignored → wrong mic), clipboard
  offer on every non-dispatched outcome, 800 ms activation repeat guard,
  CLI skips interleaved event lines via `request_id` match. Tag `v0.3.1`.
- **v0.3.0** (2026-09-11): real transcription. whisper.cpp v1.7.6 (local
  CPU build) + ggml base; worker `whisper-cli` backend proven on jfk.wav
  (1.6 s, WER≈0); room loopback toggle→paste end-to-end; sibling/user-bin
  lookup, bare-name model resolve, manifest hash + sizes corrected.
  One commit: `v0.3.0 stt`, tag `v0.3.0`. Weights never in repo.
- **v0.2.2** (2026-09-11): service readiness. Worker resolved as sibling of
  the daemon binary (systemd minimal PATH), user unit without EROFS-causing
  lockdown. Lua keybinds (`SUPER+H` etc.) in user config + runtime eval.
  One commit: `v0.2.2 service`, tag `v0.2.2`.
- **v0.2.1** (2026-09-11): UI event stream (daemon forwards state/amplitude/
  provisional to subscribers — visualizer was starved before), QML `sendOp`
  wire format (buttons sent malformed `kind`-less messages), typing-space
  notice at record start, copy-only enforced for live commits, mic-test
  levels in CLI, child reaping. One commit: `v0.2.1 ui+feedback`, tag `v0.2.1`.
- **v0.2.0** (2026-09-11): live dictation (`SUPER+H` → `vaani live-toggle`).
  Stable-prefix commits while recording (last 4 words held provisional),
  per-commit focus recheck, terminal/review preview-only, remainder on finish.
  One commit: `v0.2.0 live`, tag `v0.2.0`.
- **v0.1.0** (2026-09-10): first dependable vertical slice. Toggle dictation
  end-to-end on the laptop (capture → stub transcription → silence policy →
  copy-only insertion), event-driven overlay, settings, packaging, 31 tests.
  No model weights bundled; accuracy/latency numbers pending `manual-checks.md`.

## Commands

```sh
cargo build --workspace        # debug; --release for measurements
cargo test --workspace         # must stay green (currently 31)
qmllint ui/shell.qml ui/SettingsView.qml   # QML syntax
./install.sh                   # user-local install only (never sudo, never system upgrade)
vaani doctor                   # capability probe on the laptop
```

## Rules for agents

- Economy profile first: no new long-lived processes, no polling loops, no TCP servers.
- Audio/text never in logs, JSON, argv, or shell strings. Transcripts via stdin pipes/structured buffers only.
- State machine (`vaani-core/src/state.rs`) is the single authority — only `vaanid` transitions it; stale-session results die.
- UI is event-driven (`Socket` + `SplitParser`); QML never spawns per-tick commands.
- Terminals are copy-only; never synthesize Enter; multiline shell-like text never auto-pastes.
- Don't invent Quickshell/Hyprland/systemd APIs — check installed versions (`docs/ADR-001-environment.md`, local qmltypes, `hyprctl`, `man systemd.exec`).
- Never report container numbers as laptop measurements. Missed targets reported honestly.
- No `curl | sh`, no auto system upgrade, no edits to unrelated dotfiles in packaging.
