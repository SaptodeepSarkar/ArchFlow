# Vaani — 16 Phases

Each phase is independently usable and ends in a gate (`./TESTS/gate.sh <NN>`).
Gates 02+ unlock as components land; a gate is GREEN only on this machine, no stubs.

| # | Phase | Builds | Gate GREEN means |
|---|---|---|---|
| 01 | fixtures-contracts | nothing | 20+ formatting fixtures valid, repo contracts present |
| 02 | config-parse | 01 | sample `vaani.conf` parses, defaults apply, unknown keys warn-not-crash |
| 03 | hotkey-idle | 02 | static hyprland.lua bind + trigger script (no runtime keybind calls), idle resident under 20MB, clean shutdown |
| 04 | audio-helper | 03 | PipeWire RAM stream opens on demand, zero bytes hit disk, busy/killable flags correct |
| 05 | stt-stream | 04 | faster-whisper streams words, RTF under 0.3 on RTX 3050, unloads fully |
| 06 | pill-ui | 03 | pill shows Listening/Transcribing/Writing + error, 4-word window, cancel signal fires |
| 07 | llm-format | 01 | formatter scores 20/20 on `TESTS/fixtures/formatting.json`, p95 under 300ms |
| 08 | typing | 06 | `wtype` output byte-identical to input, clipboard copy matches, no paste path |
| 09 | key-lifecycle | 05, 07 | STT unloads before formatter loads (VRAM serialized), busy helpers never killed |
| 10 | timeouts-offload | 09 | after `idle_timeout_s`, only key service resident; memory back to baseline |
| 11 | cancel-error | 06, 09 | cancel skips formatting and offloads; STT/LLM/mic failures show error and idle |
| 12 | names-links | 02, 07 | config `[names]`/`[links]` expand verbatim end to end, longest match wins |
| 13 | integration | 08, 11, 12 | full SUPER+H to typed-text loop on 5 audio samples + all fixtures |
| 14 | soak | 13 | 3x75 scripted sentences, zero crashes, zero disk audio, gibberish declined |
| 15 | packaging | 14 | systemd user unit starts at boot, installer smoke test on fresh checkout |
| 16 | harden-release | 15 | docs-match 100%, perf numbers recorded, sign-off in vault |

## Rules

- No phase starts GREEN on stubs; hermetic stubs allowed only for the exec edge (typing), same as Kyuma's gate style.
- Phase 0 spike (see `DOCS/development.md`) runs before Phase 05/07 model commitments.
- Phase 16 ends with a vault Build Log entry: latency, soak, gibberish, docs-match, deviations owed.

---

## Phase 01 — fixtures-contracts (GREEN)

Goal: lock the formatting contract and repo skeleton before any component exists.

- [x] 20 formatting pairs covering fillers, self-corrections, names, links, punctuation
- [x] Fixture validator: unique ids, capitalized start, terminal punctuation, no filler leak
- [x] Repo contracts present: `PRD/overview.md`, `DOCS/architecture.md`, `UI/pill.qml`
- [x] `gate.sh 01` green, `gate.sh` lists all 16 gates

## Phase 02 — config-parse

Goal: `vaani.conf` is the single source of settings; nothing hardcoded in helpers later.

- [ ] Parser for all keys in `PRD/config.md` plus `[names]`/`[links]` sections
- [ ] Missing file falls back to documented defaults
- [ ] Unknown keys log a warning, never crash
- [ ] Sample `vaani.conf` in `DOCS/configuration.md` parses round-trip identical
- [ ] Gate: `gate.sh 02` parses sample, broken-sample, and missing-file cases

## Phase 03 — hotkey-idle

Goal: resident key service that listens and does nothing else, measurably small.

- [x] Trigger via static `hyprland.lua` bind + `vaani-trigger` script (no runtime keybind registration — Hyprland 0.56.2 crashes on `hyprctl eval` bind/unbind)
- [x] Pid file published for the trigger script; idle loop parses config once, handles shutdown cleanly
- [x] Log every state transition (idle, triggered, shutting down)
- [x] Gate: `gate.sh 03` checks source has zero hyprctl calls, pid file published/removed, RSS under 20MB idle, toggle run via the real trigger script

## Phase 04 — audio-helper

Goal: mic stream that provably never touches disk.

- [ ] Open default-mic PipeWire stream on request only, close on stop
- [ ] Stream shared with Vaani processes only; buffer audit in gate
- [ ] Expose busy while recording, killable after stop
- [ ] Gate: `gate.sh 04` records 5s, then proves zero new audio bytes on disk and flags correct

## Phase 05 — stt-stream

Goal: local transcription fast enough to feel live.

- [ ] Phase 0 spike first: RTF + VRAM for `small.en` on this GPU, recorded in vault
- [ ] First-run device pick: dGPU when present, else iGPU with `base.en`
- [ ] Word stream delivered to pill callback; full unload on demand
- [ ] Gate: `gate.sh 05` RTF under 0.3 on 5 samples, post-run VRAM back to baseline

## Phase 06 — pill-ui

Goal: pill driven by events, matching the PRD states exactly.

- [ ] QuickShell loads `UI/pill.qml`: Listening, Transcribing, Writing, Error
- [ ] `state` + `words` set externally; 4-word trailing window from config
- [ ] Cancel button emits `cancelRequested`; pill never takes keyboard focus
- [ ] Gate: `gate.sh 06` drives all four states plus cancel against stub events, screenshots optional

## Phase 07 — llm-format

Goal: formatter that passes every fixture on the 1.5B budget.

- [ ] Prompt/template frozen: raw transcript in, plain formatted text out, no commentary
- [ ] Rules implemented: filler strip, keep-the-correction, verbatim name/link expansion
- [ ] p95 latency measured on all fixtures
- [ ] Gate: `gate.sh 07` scores 20/20 exact match, p95 under 300ms

## Phase 08 — typing

Goal: keystrokes land where the cursor was, byte-identical.

- [ ] Type via `wtype` only; assert no paste path exists in the helper
- [ ] Copy identical output to clipboard on every run
- [ ] Start typing only after pill-hide signal (focus rule)
- [ ] Gate: `gate.sh 08` types into a scratch buffer byte-identical, clipboard matches

## Phase 09 — key-lifecycle

Goal: key service owns the STT-to-LLM handoff without VRAM overlap.

- [ ] Sequence: STT streams, STT unloads, formatter loads, transcript fed
- [ ] VRAM sampled at each step; overlap aborts the run with error state
- [ ] Busy helpers are never killed; kill request re-checks after timeout
- [ ] Gate: `gate.sh 09` runs handoff on a sample, proves serialized peaks, kills nothing busy

## Phase 10 — timeouts-offload

Goal: the machine returns to idle by itself.

- [ ] Each helper honors `idle_timeout_s` from config when killable
- [ ] Pill hides, STT/LLM/typing/audio all unloaded; key service keeps listening
- [ ] Busy past timeout is kept alive and re-checked, not killed
- [ ] Gate: `gate.sh 10` runs a full cycle, waits out the timeout, RSS back to Phase 03 baseline

## Phase 11 — cancel-error

Goal: every failure path ends idle, never stuck.

- [ ] Cancel mid-listen and mid-transcribe: no formatting pass, immediate offload
- [ ] STT load fail, LLM load fail, mic fail: error state shown, everything offloaded
- [ ] Double-trigger during a run is ignored or queued, never two pipelines
- [ ] Gate: `gate.sh 11` walks all five paths, each ends idle with zero residents

## Phase 12 — names-links

Goal: personal vocabulary works end to end from config.

- [ ] `[names]`/`[links]` loaded at boot from `vaani.conf`
- [ ] Whole-phrase match, longest wins, expansion verbatim in output
- [ ] Missing sections behave as empty, no crash
- [ ] Gate: `gate.sh 12` end-to-end spoken-to-formatted checks for each configured pair

## Phase 13 — integration

Goal: the whole loop on real audio.

- [ ] Full SUPER+H to typed-text on 5 recorded mic samples
- [ ] All 20 fixtures pass through format-to-type with stubbed window focus
- [ ] State log of a full run matches `DOCS/architecture.md` lifecycle
- [ ] Gate: `gate.sh 13` green only if 5/5 samples and 20/20 fixtures land typed

## Phase 14 — soak

Goal: prove it survives boredom and nonsense.

- [ ] 3x75 scripted sentences through format+type: zero crashes, zero stuck state
- [ ] 15 curated + 100 seeded gibberish inputs: declined or harmless, nothing destructive typed
- [ ] Disk-audio audit across the whole soak: still zero bytes
- [ ] Gate: `gate.sh 14` reports counts (ok/noop/crashes) with thresholds from Phase 13

## Phase 15 — packaging

Goal: installable by someone who is not us.

- [ ] systemd user unit: key service starts at boot, restarts on failure, logs to journal
- [ ] Installer script: checks deps (`pipewire`, `wtype`, `quickshell`), installs unit + default config
- [ ] Uninstall removes unit, config kept with a warning
- [ ] Gate: `gate.sh 15` runs installer on a fresh checkout into a temp prefix, unit starts, hotkey live

## Phase 16 — harden-release

Goal: numbers, docs, sign-off — release only when all three agree.

- [ ] Latency table: hotkey-to-pill, word stream RTF, format p95, all measured live
- [ ] Docs-match: every behavior in `PRD/` and `DOCS/` has a passing gate; mismatches listed as owed, not silently fixed
- [ ] Vault Build Log entry: numbers, soak results, gibberish verdicts, deviations
- [ ] Gate: `gate.sh 16` verifies docs-match 100% and a signed-off Build Log exists
