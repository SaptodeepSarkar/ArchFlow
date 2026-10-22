# AGENTS.md — working guide for AI agents

Read this before changing code. The map is `DOCS/layout.md`; behaviour is
`DOCS/architecture.md`. Repo: `SaptodeepSarkar/ArchFlow`, branch `main`.

## What this is

Vaani: local-first voice typer for Linux. SUPER+H → mic → STT → on-device LLM
formatter → `wtype` types the text where the cursor is. Rust workspace, a
Quickshell QML overlay, and Python STT backends. Nothing leaves the machine and
mic audio never touches disk.

## Commands

```sh
cargo build --workspace          # build everything
cargo test --workspace           # unit tests (live model tests are #[ignore]d)
bash TESTS/ci.sh                 # the hermetic CI gate set — run before pushing
./TESTS/gate.sh                  # full gate board with status
./TESTS/gate.sh 07               # one gate
./install.sh                     # install binaries, unit, overlay
```

## CI

`.github/workflows/ci.yml` runs on every push/PR to `main` and `vaani-scaffold`:
`TESTS/ci.sh` (shell + python syntax, workspace build/tests, hermetic gates
01,02,07,10,11,12,19) plus a gate-inventory check. The rest of the board needs a
mic, PipeWire, a compositor, a GPU or a model server, so it only runs on the real
machine. `.github/workflows/release.yml` runs on a `v*` tag: hermetic gates,
release build, tarball, GitHub release.

## Done means a green gate

Every phase in `DOCS/phases.md` owns `TESTS/gates/gate-NN.sh`, wired into the
`GATES` list in `TESTS/gate.sh`. Gate 16 is the meta-gate: it checks the docs and
the board still agree. A change is finished when its gate is green locally and
CI is green — not when the code compiles.

## Invariants — do not break these

- **Audio stays in RAM.** No recording reaches disk, not even a temp wav.
- **STT and the formatter are never in VRAM at once.** STT unloads before
  formatting starts; a helper reporting busy is never killed.
- **No runtime keybinds.** Hyprland 0.56.2 crashes when an app registers binds;
  the static bind calls `packaging/vaani-trigger`, which signals the daemon.
- **A missing model costs accuracy, never the utterance.** No refine server →
  streaming words; no formatter → the deterministic rule engine.
- **Config is read once** by `vaani-config` from `~/.config/vaani/vaani.conf`,
  including `[names]` / `[links]`. Env vars (`VAANI_*`, see
  `DOCS/configuration.md`) select backends, endpoints and owned model servers.

## Layout in one line each

- `crates/<component>/` — one crate per component, logic in `lib.rs`, its binary
  in `src/bin/`.
- `TESTS/` — gate harness, fixtures, drivers, log convention
  `/tmp/vaani-gate-NN.log`.
- `UI/quickshell/` — the pill overlay; preview with `qmlscene`.
- `packaging/` — systemd unit, trigger script, model server launchers.
- `DOCS/`, `PRD/` — architecture and the specs the gates assert.
- `target/`, `.research/` — gitignored; trained models ship as release assets.

## Conventions

- Commit messages describe the behaviour change in one sentence; no prefix
  required.
- Releases are annotated `vX.Y.Z` tags; the release workflow does the packaging.
- If a shortcut has a known limit, leave a `shortcut: <limit>, <when to
  upgrade>` comment next to it.
- Update `DOCS/` with the code — gate 16 fails otherwise.
