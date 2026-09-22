# Manual checks (remaining, on the laptop — not fabricated)

Run after `tools/model-setup.py --model base` + service start. Tick honestly.

## Uncertain integrations (spec §15.2)
- [ ] Overlay appears bottom-center 300×56 on the dictation monitor, no kbd focus
- [ ] `pw-record` bounded capture: 5/30/120 s utterances land in worker
- [ ] Unicode paste (en/hi/bn) into a harmless text field; no accidental Enter

## Behaviours
- [ ] Toggle, key-repeat ignore, fast press/release, hold-to-talk release paths
- [ ] SUPER+H live: provisional words appear only in the overlay; no target
  application receives text until final transcription and delivery policy run
- [ ] Live focus change mid-session: preview continues, recording continues,
  full text recoverable via copy (no duplicates on finish)
- [ ] Final terminal delivery: cleaned text appears, no synthetic Enter or
  command execution; review and copy-only remain clipboard-only
- [ ] Live worker hiccup: session survives, next tick retries
- [ ] Cancel during STARTING / RECORDING / TRANSCRIBING / CLEANING / INSERT-prep
- [ ] Silence → no text; low-volume; background noise
- [ ] Mic unplug mid-capture → "Microphone disconnected" + recovery offered
- [ ] Default-device change between sessions; PipeWire restart during capture
- [ ] Worker crash → controller alive, ERROR + retry; UI crash → capture stops
- [ ] Target closes / focus changes / cursor moves / settings opened mid-op
- [ ] Screen lock / suspend / logout during recording
- [ ] Clipboard manager running: no double-paste, no clobber of newer copies
- [ ] 20 successive dictations → idle: no workers/streams/GPU ctx, RSS budget
- [ ] Malformed/oversize IPC, stale socket, duplicate clients, bad version

## Accuracy (fixtures in tests/fixtures, approved non-sensitive)
- [ ] WER set (en, names/numbers/negations split) — report n + limits
- [ ] CER sets (hi, bn) — report n + limits
