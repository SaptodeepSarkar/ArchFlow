# Troubleshooting

- Dictation only copies instead of typing → older configs may still contain
  `insertion.mode = "copy-only"`; restore typing with
  `vaani config-set insertion.mode automatic`.
- `cannot reach vaanid` → `systemctl --user status vaanid` (user unit, not root).
- `capture failed` → PipeWire running? `pw-record --help`; EasyEffects virtual
  source selectable via audio.device_selector (stable name).
- `Microphone disconnected` → input vanished; captured audio kept for explicit
  `vaani recover`/`vaani copy`, retry, or `vaani discard`. Future sessions
  re-resolve the default source; never hot-swaps mid-utterance.
- `Text ready — target changed` → focus moved; nothing forced back. Copy/review.
- `Paste requested` ≠ confirmed inserted — delivery can't be confirmed; check.
- Terminal got no typed text → check that it retained focus and that `wtype`
  is available. Vaani never synthesizes Enter or executes the prompt.
- Transcription failed → worker crash leaves controller up; audio kept briefly
  for retry with visible controls and bounded expiry.
- Clipboard replaced → expected in automatic mode; restoration
  only of our own bounded plain-text snapshot, never clobbering newer copies.
- Lock/suspend during recording → capture cancelled, insertion forbidden for
  that op; re-unlock before next recording. If lock detection is unavailable
  on your setup, automatic insertion is disabled (documented, not silent).
- Model download interrupted → tmp file removed, rename never happens; rerun
  `tools/model-setup.py` (checksum enforced with --sha256).
- Memory-only handling is NOT a guarantee against swap/crash dumps/same-user
  readers — stated plainly, not oversold.
