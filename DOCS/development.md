# Development

## Prereqs (all present on this machine)

`cargo`, `pipewire`, `wtype`, `quickshell`, `qmllint`, `python3`.

## Layout

Rust workspace comes later (Phase 1). For now: `PRD/` spec, `DOCS/` guides, `TESTS/` gates + fixtures, `UI/` pill.

## Tests

```sh
./TESTS/gate.sh 01   # fixtures + contract checks (green now)
./TESTS/gate.sh      # list all gates and their status
```

Gates 02+ unlock as components land; each gate doc lives next to its component PRD.

## Phase 0 spike (do this before any daemon code)

1. Stream faster-whisper `small.en` over 5 mic samples; record RTF + VRAM.
2. Run the 1.5B Q4 formatter over `TESTS/fixtures/formatting.json`; record p95 + exact-match rate.
3. If combined peak exceeds 5GB or fixtures drop under 18/20, stop and revise model picks before building.
