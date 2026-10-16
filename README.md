# Vaani

Local-first voice typer for Linux. Press SUPER+H, speak, get cleaned text typed where your cursor is. STT transcribes, a small on-device LLM formats (filler removal, custom names, spoken URLs), `wtype` types it. Nothing leaves the machine; mic audio never touches disk.

## Layout

- `PRD/` — requirements, per component. Start at `PRD/overview.md`.
- `DOCS/` — architecture, configuration, development guides.
- `TESTS/` — phase gates (`gate.sh <NN>`) + fixtures. Start green with `./TESTS/gate.sh 01`.
- `UI/` — QuickShell QML pill previewable with `qmlscene`.

## Status

Scaffold + Phase 0 spike pending. Full hypothesis and model picks live in the vault: AgentsMemory `Projects/Vaani/Hypothesis.md`.
