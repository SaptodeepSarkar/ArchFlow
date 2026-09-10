# Fixtures — approved, non-sensitive, synthetic reference sentences.

- `en.ref`: 5 short English utterances incl. negation ("do not delete"),
  numbers, and a name. Score with `tools/wer.py --lang en` (WER).
- `hi.ref` / `bn.ref`: 3 lines each, everyday phrases. Score CER
  (`--lang hi|bn`). Character-level by design for abugida scripts.
- Record each line as 16 kHz mono wav (5–10 s), keep filenames aligned, then:
  `python3 tools/wer.py --ref tests/fixtures/en.ref --hyp your-hyp.txt`
- Never call one sentence a benchmark. Report n, model, backend, threads,
  power mode, cold vs warm, and names/numbers/negations separately.
