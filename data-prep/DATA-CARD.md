# Data card — Vaani V8 training data

Private, local training data. Do not publish the audio or the speaker IDs.

## STT

- **Source:** `ishands/commonvoice-indian_accent` (Hugging Face), a public,
  non-gated re-upload of Mozilla Common Voice 21 English recordings filtered to
  Indian accents: 110,088 clips / 163.89 h before our filters.
- **Used:** 43,341 clips / 66.4 h total (64.64 h train, 1.01 h dev, 500-clip
  test). 1,422 train speakers, 117 dev, 77 test; speaker-disjoint.
- **Licence:** the mirror card declares **no licence field**. The underlying
  Common Voice data is CC0. Treat this copy as private until the mirror's
  provenance is confirmed; do not redistribute it.
- **Privacy:** voice recordings are personal data. Speaker IDs are Common Voice
  client hashes; keep them out of public releases.
- **Processing:** mp3 → 16 kHz mono PCM16 wav, peak unchanged, no denoising.
  Transcripts keep the provided casing/punctuation; whitespace collapsed.
- **Filters:** 1–30 s, 1–200 chars, ≥3 words, `up_votes >= 2`,
  `down_votes == 0`, accent string contains `india`.
- **Known gap:** no WER filtering; accents are self-reported.

## Formatter

- **Tatoeba English** sentences, 5–25 words — CC-BY 2.0. Attribution:
  Tatoeba contributors, https://tatoeba.org.
- **GoEmotions** (`google-research-datasets/go_emotions`) — Apache-2.0. Used
  only for tone seeds (anger, annoyance, excitement, gratitude, realization).
- **Hand-written templates** in `prepare_formatter.py` — CC0.
- **Clean side:** always human text. **Noisy side:** generated with deterministic
  rules; no LLM-written targets.
- **Split:** by `seed_id`, 80/10/10; no seed crosses splits.
- **Mix:** asr 6,000; filler 4,000; repair 3,600; identity 2,400; entity 1,600;
  tone 1,200; code-switch 800; adversarial 400.
- **Known gap:** 8.25% of rows carry a rule-6 vocab mapping (entity slice),
  below the contract's ~20%; mean disfluency density 10.23%.

## Intended use

Fine-tuning `openai/whisper-large-v3-turbo` and
`Qwen/Qwen2.5-1.5B-Instruct` for the Vaani local voice typer. Not for
surveillance, speaker identification, or public redistribution.
