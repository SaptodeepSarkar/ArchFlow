# V6 STT held-out challenge plan

This is a qualification plan, not training data or a claim of measured
accuracy. Keep challenge audio and references in the non-Git workspace. Never
train on the frozen challenge split. Each row should carry `challenge_tags`
and, for term-focused rows, an exact `challenge_terms` list understood as the
reference spelling required by that sample.

## Recognition contract

V6 STT transcribes the audible utterance. It must not infer a speaker's
intended wording, remove disfluencies, repair grammar, or silently normalize
an unheard word. In particular, preserve spoken fillers and repetitions in
the raw reference/hypothesis; downstream V6 formatting is responsible for
cleanup. Keep the V6 formatter out of the acoustic WER measurement.

## Challenge categories

Use held-out real speech first. A human reads or speaks each prompt and an
annotator verifies the audio-to-reference match. Store tag names in the
evaluator's lowercase identifier form.

| `challenge_tags` | Coverage to collect | Example term(s) / check |
| --- | --- | --- |
| `acronym` | Acronyms inside natural sentences, not isolated spelling lists | `LLM`, `STT`, `TTS`, `ASR`, `GPU`; report exact protected-term recall |
| `spoken_letters` | Letter-by-letter pronunciations with acoustically similar letters | `L-L-M`, `L M`, `S-T-T`; annotate the conventional written form only when the reference policy calls for it |
| `confusable_lexical` | Fast connected function words, near-homophones, and plural endings | `and`/`ant`, `ands`/`ants`; use verified audio references and never resolve from world knowledge |
| `technical_entity` | Frameworks, model formats, runtimes, package names, versions | `GGUF`, `CTranslate2`, `whisper.cpp`, `Android`, `V6` |
| `indian_english` | Diverse South Asian English speakers and common regional names/terms | Preserve the speaker's words; don't infer a location or entity from accent |
| `code_switch` | Genuine mixed-language turns, including English technical terms in Hindi/Hinglish | Keep the spoken languages; record the reference's writing script explicitly |
| `filler_verbatim` | Audible `uh`, `um`, `er`, or similar words, including words discussed metalinguistically | STT reference retains the audible filler; don't score formatter deletion here |
| `repetition_verbatim` | Repeated words, false starts, and repaired starts | Preserve what is audible in raw STT, e.g. `I, I think...`; separate acoustic omission from later cleanup |
| `pause_boundary` | Sentence boundary vs hesitation pauses | Evaluate against verified words; punctuation is reported separately from lexical WER |
| `quiet_speech` | Quiet but intelligible speech at realistic mic levels | Ensure the source reference is fully audible before inclusion |
| `fast_speech` | Fast connected speech and reductions | Don't let a language-model-plausible word substitute for the audible one |
| `noise_overlap` | Room noise, device noise, and overlapping speakers | Mark overlap/noise condition; exclude unrecoverable reference spans or annotate them consistently |
| `short_utterance` / `long_utterance` | One- or two-word turns and longer turns near deployment limits | Measure empty outputs, truncation, repetition, and latency as well as WER |
| `numbers_units` | Spoken numbers, dates, versions, and units | Define one written-reference normalization policy before scoring |

## Split and metrics

- Split by speaker (and by conversation/session where applicable), never by
  random clip alone. Keep train/dev/test speakers disjoint; freeze the test
  manifest hash before comparing model variants.
- Report corpus-normalized WER, per-tag normalized WER, decode failures,
  real-time factor, and protected-term recall. Use the aggregate-only
  `tools/eval_v6_android_stt_export.py` fields `challenge_tags` and
  `challenge_terms`; do not serialize references or hypotheses to reports.
- Report row-level distributions privately only if the dataset's access
  terms allow it; published/repository results remain aggregate-only.
- `tools/eval_v5_whisper_adapter.py` defaults to its existing forced-English
  decode for historical comparability and now accepts `--language auto` for
  Whisper's per-clip language detection. WER normalization preserves Unicode
  letters and combining marks, so Hindi-script references are not silently
  reduced to empty strings. Compare fixed-language and autodetect modes on the
  same speaker-held-out code-switch set before choosing a deployment setting.
- Compare original Whisper-small, corrected clean V6, and each decoder
  context setting on the exact same audio and decode options. Test configured
  hotwords both on and off; don't claim a term pack helps from training loss
  or a text-only test.
- Do not use the rejected Deepgram Flux TTS corpus or descendants. Any future
  TTS-derived examples need a separately audited generator/voice license,
  explicit `synthetic` provenance, actual-target-STT hypotheses, and a
  speaker/voice-disjoint evaluation design.

## Current coverage and acquisition gate

The current AMI split contains only 3 matching clips across Vaani's combined
79-term acronym/mobile packs (train 3, dev 0, test 0); it cannot validate the
technical-token categories. Mozilla Common Voice Scripted Speech 26.0 South
Asian English is the next clean accent/lexical source, and validated Common
Voice Spontaneous Speech 5.0 is the next audited filler/repetition source.
Both releases are documented in `docs/V6_DATASET_AUDIT.md`; the MDC account
owner must accept the release terms in its web UI before authorized download.

The VoiceArena Monsoon en-IN public split is evaluation-only. Its pinned
revision and human-review/consent/licensing details are in the dataset audit.
`tools/stage_v6_monsoon_eval.py` streams that exact revision, writes only
audio and reference text to an ignored user-local directory, and removes the
temporary raw Hub cache (which contains demographic fields). Run the aggregate
test once, only after freezing the candidate and decoder settings; never use
its score to tune a second candidate or vocabulary pack.
