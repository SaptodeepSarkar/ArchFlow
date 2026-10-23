# Vaani

Local-first voice typer for Linux. Press SUPER+H, speak, get cleaned text typed where your cursor is. STT transcribes, a small on-device LLM formats (filler removal, custom names, spoken URLs), `wtype` types it. Nothing leaves the machine; mic audio never touches disk.

## Layout

- `PRD/` — requirements, per component. Start at `PRD/overview.md`.
- `DOCS/` — architecture, configuration, development guides.
- `TESTS/` — phase gates (`gate.sh <NN>`) + fixtures. Start green with `./TESTS/gate.sh 01`.
- `UI/` — QuickShell QML pill previewable with `qmlscene`.

## Status

Scaffold + 16 phases / 22 gates (`DOCS/phases.md`). `./TESTS/gate.sh` runs the
board on the machine — 22/22 GREEN on 2026-10-24. `bash TESTS/ci.sh` is the
hermetic set CI runs on every push/PR: build, workspace tests, the pure-logic
gates, and gate 22, which drives the real daemon end-to-end against stub
mic/STT/typing backends (no mic, compositor, GPU or model server). Full
hypothesis and model picks live in the vault: AgentsMemory
`Projects/Vaani/Hypothesis.md`.
