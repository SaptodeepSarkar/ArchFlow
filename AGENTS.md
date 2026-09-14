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

- **v0.8.3** (2026-09-11): pure final. Finalize always runs full-utterance
  inference (long audio via overlapping same-model segments); live-tick
  fragments are preview-only after proving 2 s windows diverge into salad
  ("asked to ask you"). One commit: `v0.8.3 pure-final2`, tag `v0.8.3`.
- **v0.8.2** (2026-09-11): message-safe transcripts. Local polish collapses
  false starts ("genuine genuinely") and duplicate phrases ("i can't i can't")
  while keeping intentional emphasis ("very very", "no no"); `cleanup.
  vocabulary` appends names/terms to the recognizer prompt. Misheard content
  words are never guessed. One commit: `v0.8.2 polish`, tag `v0.8.2`.
- **v0.8.1** (2026-09-11): streaming that actually streams. Unique temp
  dirs per job (shared paths let a finished call delete a sibling's wav —
  every server call fell back to slow one-shot), offline hub flags (load
  ~1 s, chunks ~0.3 s), silence trim + no-speech filter against phantom
  phrases, padded-audio regression test. One commit: `v0.8.1 fw-stream-fix`,
  tag `v0.8.1`.
- **v0.8.0** (2026-09-11): streaming fine-tuned STT. Directory models run
  through a persistent faster-whisper sidecar (loads once, ~0.3 s per chunk,
  ~90 MiB resident, reaped after `server_idle_secs`), so cozy shows results
  on the go; filler-strip shared in core; hardware streaming test (ignored).
  One commit: `v0.8.0 fw-stream`, tag `v0.8.0`.
- **v0.7.2** (2026-09-11): pure final. The live-preview seed is only merged
  into the final transcript when preview and final models agree; with split
  models (base preview, cozy final) the final model transcribes the whole
  utterance so base-model wording can't corrupt it. One commit:
  `v0.7.2 pure-final`, tag `v0.7.2`.
- **v0.7.1** (2026-09-11): backend visibility. `vaani status` latencies now
  carry the STT backend label (`fw-ct2` vs `whisper-cli-cuda` vs `cpu-stub`)
  so a wrong-model regression is caught from numbers. One commit:
  `v0.7.1 backend-tag`, tag `v0.7.1`.
- **v0.7.0** (2026-09-11): fine-tuned speech. `recognition.model = "cozy"`
  runs the Cozy whisper-small LoRA (Indian English + your voice) via a
  faster-whisper sidecar (CT2 int8, beam 1, CUDA; user-local copy, weights
  never in repo); `recognition.live_model` keeps preview ticks on fast
  whisper.cpp. Model resolution prefers real artifacts (a stale `cozy.bin`
  path rescues to the `cozy/` directory instead of silent cpu-stub), and the
  sidecar carries Cozy's validated Hindi prompt by default. Vocabulary feeds
  the recognizer prompt (names), filler words (uh/um/er/mmm) are stripped in
  the worker. One commit: `v0.7.0 cozy-stt`, tag `v0.7.0`.
- **v0.6.5** (2026-09-11): place-tracking preview. At most five recent words:
  dim trailing context plus the newest word highlighted, so no ellipsis hides
  your place. One commit: `v0.6.5 place`, tag `v0.6.5`.
- **v0.6.4** (2026-09-11): running preview. The overlay shows the last ~24
  recognized words (three wrapped lines) with a quick fade on arrival instead
  of a fixed two-word slot, so speech is never dropped from the display
  between ticks. One commit: `v0.6.4 preview`, tag `v0.6.4`.
- **v0.6.3** (2026-09-11): no-wedge completion. Every clipboard/dispatch
  helper runs under a 5 s deadline, and wl-copy offers reap instead of
  draining pipes (its forked server holds them open, which wedged sessions
  in INSERTING deaf to Super+H); a second press inside the first 1.2 s of
  recording is key bounce, not a discard. One commit: `v0.6.3 no-wedge`,
  tag `v0.6.3`.
- **v0.6.2** (2026-09-11): finish-stage Super+H is a harmless "finishing…"
  instead of discarding the transcript; the "Copied to clipboard" flag rides
  on the Idle state event so auto-stop shows the ~2 s popup; centered live
  words with fade-in newcomers and slide-left successors. One commit:
  `v0.6.2 finish+overlay`, tag `v0.6.2`.
- **v0.6.1** (2026-09-11): copy-first completion. `copy-only` is the default
  insertion mode (injection code kept for `automatic`); every finish shows a
  "Copied to clipboard" popup that lingers ~2 s. Live preview no longer
  blanks on pause/partial-word ticks or worker hiccups — last-known words
  stay on screen, with tick failures logged. One commit: `v0.6.1 copy+preview`,
  tag `v0.6.1`.
- **v0.6.0** (2026-09-11): incremental live transcription and dependable
  completion. One-second chunks with overlap replace cumulative re-inference;
  finalization processes only the unconsumed tail. VAD gate lowered to 0.003
  so quiet microphones trip end-of-speech auto-stop. wtype virtual-keyboard
  paste replaces unreliable compositor synthesis; terminals use primary
  selection + Shift+Insert (single modifier) while GUI apps use clipboard +
  Ctrl+V — completion always leaves the full transcript on the clipboard AND
  requests paste. Review-gated sessions copy to clipboard and close to Idle
  instead of parking on "Text ready", and the overlay auto-exits from READY.
  One commit: `v0.6.0 streaming+insertion`, tag `v0.6.0`.
- **v0.5.2** (2026-09-11): insertion handoff hardening. Verify clipboard
  readiness, recheck focus immediately before paste dispatch, log non-content
  outcomes, and slide the overlay down after paste or clipboard fallback. One
  commit: `v0.5.2 insertion+exit`, tag `v0.5.2`.
- **v0.5.1** (2026-09-11): live hardware follow-up. Quiet-microphone VAD
  tuning, CUDA whisper.cpp setup, and an overlay containing only the waveform
  and two-word transcript/status text. One commit: `v0.5.1 live+cuda`, tag
  `v0.5.1`.
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

## Long-running V5 training handoff

- The full public Indian-English corpus is local at
  `/home/saptodeep/Projects/Cozy/stt-finetune/data/cv_indian_full/` (3,987
  public clips; weights/audio/manifests stay out of Git).
- For the expanded V5 manifest, use `tools/build_v5_mixed_manifest.py` with
  the deterministic 100-row holdout excluded. The V5 Whisper trainer supports
  `--streaming`; use it for the full corpus because eager mel-feature building
  exhausts host memory. A one-step streaming smoke test passed on 2026-09-14.
- Do not suspend the laptop or kill `awake` at any stage. After the complete
  STT and LLM training/evaluation scope (including any active TTS experiment)
  is genuinely finished and the final benchmark brief is delivered, open
  Spotify, start playback, open the Speakers/device selector, and select the
  Echo Dot. This media action must not happen after an STT-only milestone and
  must not be claimed complete without verifying the selected device.
- Verified Spotify/Echo Dot navigation on 2026-09-14: Spotify is tagged into
  Hyprland's `special:music` workspace; toggle it with
  `hyprctl repl 'hl.dispatch(hl.dsp.workspace.toggle_special("music"))'`.
  Spotify exposes a local CDP endpoint on `127.0.0.1:9222`; click the button
  with `aria-label="Play"`, then the button with
  `aria-label="Connect to a device"`, then the first device-picker row whose
  visible name is `Saptodeep's 2nd Echo Dot`. Verify the result by observing
  an `aria-label="Pause"` control and Spotify's `Now playing:` status. Do not
  infer success from process state alone.
