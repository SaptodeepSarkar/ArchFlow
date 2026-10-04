# V6 Android STT Architecture

Status: implementation plan and evidence record. No V6 STT model is promoted
or Android-qualified by this document.

## Decision

V6 Android STT must remain an offline, CPU-first `whisper.cpp` path, but it
must be fed by a **fused Hugging Face Whisper checkpoint**, never the Linux
CTranslate2 directory. The candidate is the V5/Cozy Indian-English
Whisper-small checkpoint only after a reproducible export, accuracy comparison,
timestamp check, quantization experiment, and physical-device benchmark.

This preserves a single model family across Linux and Android while keeping the
platform-native artifact formats separate:

```text
fused HF Whisper checkpoint
        |                         \
        v                          v
Linux: CTranslate2 / faster-whisper Android: whisper.cpp-compatible ggml
        |                          |
  final STT metadata        final STT metadata
        \                          /
         -> V6 formatter -> insertion
```

The Android runtime must not attempt to load a CTranslate2 directory. The
current Android binding consumes a `ggml` Whisper artifact; a prospective
format migration must be demonstrated against the binding before changing the
release manifest.

## Vocabulary is not a file-size switch

The Android baseline is an English Whisper Base artifact. The locally retained
fused V5/Cozy checkpoint is standard Whisper-small and has a 51,865-token
Whisper tokenizer; replacing Base with that checkpoint would retain its
multilingual BPE vocabulary, which is the correct starting point for Indian
English, Hindi, and Hinglish. It does **not** safely permit adding arbitrary
vocabulary tokens at conversion time: the encoder/decoder embedding rows and
tokenizer IDs must remain aligned.

The practical V6 vocabulary plan is therefore:

1. export the fused multilingual fine-tuned checkpoint together with its exact
   tokenizer files and checksums;
2. retain the model's original tokenizer unchanged through conversion and
   quantization;
3. evaluate vocabulary prompts / decoder context for user-provided names and
   technical terms, without treating them as factual correction authority;
4. add training examples for Hinglish, technical tokens, letter sequences, and
   URLs only through a licensed, split-safe STT data pipeline;
5. consider tokenizer expansion only as a separate retraining project with
   reinitialized embeddings and a full Android requalification—not as an
   export-time edit.

OpenAI's Whisper documentation distinguishes multilingual models from
English-only variants, and its multilingual tokenizer is designed to encode
non-English text efficiently. [OpenAI Whisper model card](https://github.com/openai/whisper/blob/main/model-card.md)
[documents the model families](https://github.com/openai/whisper/blob/main/README.md).

## Current Android evidence

Environment check on 2026-09-30 found an Android emulator attached
(`emulator-5554`, x86_64); it is not a physical arm64 phone. The complete
Android unit suite was recompiled and rerun (21 tests, zero failures), including
V6 tokenizer, local inference, and tagger tests. This validates JVM behavior,
not native STT accuracy, physical-device memory/latency, or V6 model quality.
No V6 STT artifact has been installed or selected.

Availability recheck on 2026-10-03: `adb devices -l` returned no attached
devices. The earlier emulator check above is historical; currently there is
neither an emulator for app-integration smoke tests nor a physical arm64 device
for resource/latency qualification. Recheck device availability before
planning an Android runtime test; do not treat host export tests as device
qualification.

`NativeWhisperStt` uses 16-kHz mono PCM, writes a private temporary WAV, and
runs the user-installed model via the ARM64 `whisper-android` binding. That
binding is a thin `whisper.cpp` wrapper; its API returns final text and actual
segment start/end timing, but no word-level timing, token confidence,
no-speech probability, or alternatives. V6 must represent those unsupported
fields as unavailable, not invent values.

As of this record, Vaani now carries final backend identity and genuine segment
timings in `SttFinalEvidence` / `SttSegmentEvidence`. The app's formatter still
receives plain final text: enriching formatter input with timing must be a
separate, evaluated protocol change, not an invisible behavioral change.
Android service boundaries also fence each STT generation: a queued completion,
error, RMS, or delayed UI update from a cancelled attempt is ignored once a
newer attempt has begun. This protects insertion from stale final text while
keeping native cancellation cooperative.

The underlying runtime is viable on Android: upstream `whisper.cpp` lists
Android support, maintains an Android sample, and supports integer quantized
Whisper artifacts. [whisper.cpp README](https://github.com/ggml-org/whisper.cpp/blob/master/README.md)
[documents quantization](https://github.com/ggml-org/whisper.cpp/blob/master/README.md),
and its [Android sample](https://github.com/ggml-org/whisper.cpp/blob/master/examples/whisper.android/README.md)
is a useful API/build reference. This is portability evidence, not an Android
performance claim for Vaani.

## Contextual vocabulary API check — 2026-10-04

The Android app pins `dev.ffmpegkit-maintained:whisper-android:1.0.0` in
`android/app/build.gradle.kts`. Inspection of the resolved AAR's public JVM
API confirms `WhisperConfig` exposes only `language`, `translate`, `threads`,
`maxSegmentLength`, and `printTimestamps`; it has no `initial_prompt`,
hotword, or decoder-context parameter. The upstream package documents the
same file-backed `Whisper.transcribe(model, audioPath, config)` interface
([upstream API](https://github.com/ffmpegkit-maintained/whisper)). Therefore
the current Android path cannot use a user vocabulary to bias Whisper's
acoustic decoding.

Android's `PersonalizationStore` currently applies spoken-alias to canonical
spelling replacements after recognition and formatting in
`VoiceOverlayService` / `VaaniImeService`. That is useful for a user-known
term, but it is a deterministic spelling correction, not an STT vocabulary
gain. Keep those two measurements separate.

The first Linux human-speech diagnostic (32 fixed AMI dev rows) compared the
same V5 CT2 model with the global mobile technical-term pack off/on. WER moved
from 17.9028% to 25.5754%; that suite had no annotated protected terms, so it
cannot measure whether relevant names improve. This is a warning against
blindly applying a broad global list, not a rejection of targeted hints. The
full evidence and privacy-safe reports are recorded in
[`V6_STT_TRAINING.md`](V6_STT_TRAINING.md). Next, use a human-speech suite with
annotated, held-out relevant terms plus ordinary-speech negatives; test
bounded/relevance-filtered prompts and report WER, term recall, and false
substitutions together. If that clears the gate, port by extending or
replacing the Android JNI binding; pass hints in-memory, never through
argv/logs, and retain opt-in per-user vocabulary semantics. Do not change
Android model selection based on the diagnostic: mobile prompting needs its
own fixed-audio and physical-device qualification.

## Conversion and qualification gates

1. Pin a whisper.cpp source revision and record its converter, build flags,
   fused-checkpoint SHA-256, tokenizer checksums, and output SHA-256.
2. Export from the fused HF checkpoint. Refuse a CT2 directory as input.
3. Before quantization, compare HF and exported float artifacts on a fixed,
   license-cleared 100-clip suite. Capture normalized WER, per-language and
   Hinglish behavior, segment timing coverage, invalid-token rate, and
   recognizer backend/version.
4. Compare float, Q8, and an appropriate smaller quantization on the same
   suite. Do not select a quantization solely by disk size.
5. Ship the candidate beside Android Base Whisper. Verify release-manifest
   checksum, model load, final text, segment timing, cancellation, and retry.
6. On a physical arm64 Android device, measure cold/warm peak PSS/RSS, RTF,
   end-of-utterance latency, battery/thermal behavior, WER, Hinglish, and
   timestamp availability. Emulator and host figures are not Android results.
7. Replace Base Whisper only if it does not regress acceptable WER/latency/
   memory and all metadata required by V6 is genuinely available.

## Required engineering work

| Area | Current behavior | V6 requirement |
| --- | --- | --- |
| Model provenance | Linux Cozy is CT2; Android Base is ggml | Record fused HF source and derive each platform artifact independently. |
| Decoder metadata | Android now exposes final segment timestamps | Add a V6 protocol boundary for optional timing; retain `None` for unavailable word confidence/alternatives. |
| Streaming | Android records a final private WAV then transcribes | Keep preview STT-only; evaluate chunked native decoding only after the final path is accurate. |
| Lifecycle | Model is loaded/released per final utterance | Benchmark per-utterance versus safely reusable native context before adopting residency. |
| Model selection | Base and an unpromoted V6 candidate have separate verified package slots | Require artifact version, tokenizer hash, language/metadata capability flags, and explicit qualification before selection changes. |
| Safety | Raw STT is formatter input | Never use an STT vocabulary prompt or formatter to guess unsupported content. |

## Known issues and non-goals

- The installed binding exposes only segment timing; word timestamps,
  probabilities, no-speech scores, and meaningful alternatives are not
  available through its public API.
- The binding's `WhisperConfig` surface does not expose the complete
  whisper.cpp decode/metadata control set. A V6 metadata upgrade may require a
  maintained JNI fork or an upstream API extension.
- Android model delivery now stages a qualified future V6 candidate as
  `ggml-v6.bin`, independently of the `ggml-base.bin` fallback. The downloader
  rejects a model whose manifest runtime does not match that slot and rejects
  duplicate slots. It deliberately does not auto-select the candidate; its
  tokenizer, WER, timing, memory, and latency gates still decide promotion.
- The existing 923 MiB float export is a format/load/decode sanity result only.
  It is not a mobile artifact and must not be installed or benchmarked as one.
- Fine-tuning, quantization, or a different Whisper architecture must be
  backed by license/provenance checks, speaker-isolated splits, and automated
  held-out quality and regression gates. The active V6 path does not require
  per-row user review: ambiguous or mismatched examples are automatically
  excluded and are never silently promoted as gold.

## Immediate next experiment

The fresh-base, 1,500-step context-heldout candidate completed, but failed its
vocabulary gate (candidate WER 15.54% vs. 11.86% base; protected-term accuracy
66.05% vs. 74.07%). Its paired AMI-dev comparison also failed the protected-term
gate: WER improved from 34.69% to 26.92%, but protected-term accuracy fell from
33.33% to 11.11% on nine supported terms. It remains quarantined.

The fresh-base 5% vocabulary-sampling candidate has now completed its paired
evaluation. It improved normalized WER on vocabulary holdout (11.67% to 6.64%),
AMI dev (34.69% to 23.72%), and ICSI dev (15.78% to 8.43%), but protected-term
accuracy remained 73.46% on vocabulary holdout (below the 99% requirement) and
regressed on AMI (33.33% to 22.22%) and ICSI (63.79% to 55.17%). It is
rejected. The fresh-base 20% sampling follow-up has also completed. On the
seen-term context holdout, WER improved from 11.6698% to 3.5104%, but protected-
term accuracy reached only 83.33% (135/162), below the 99% gate. On all 3,121
AMI dev examples, WER improved from 34.6903% to 25.6326% while protected-term
accuracy fell from 33.33% (3/9) to 22.22% (2/9). On the 861-row ICSI dev subset,
WER improved from 15.7783% to 11.4888%, while protected-term accuracy fell
from 63.79% (37/58) to 58.62% (34/58). The candidate is rejected because it
regresses protected terms on both speech suites and misses the vocabulary gate;
do not export or integrate it. The separate ICSI test split remains untouched.

The expanded 12-frame / two-voice synthetic context pack is staged in the
builder but has not yet been generated. Its clips can test lexical/context
coverage, not Indian accents or spontaneous speech. After the active formatter
training releases the local CPU/GPU, generate the expanded pack and retrain a
fresh-base STT candidate; retain AMI and ICSI dev gates, and add qualified
Indian-English speech rather than treating synthetic American English as a
substitute. Export is still gated on every applicable WER and protected-term
criterion passing.

After training-set development gates pass, pass the exact base checkpoint,
candidate adapter, and all applicable passing aggregate reports to the exporter.
It fuses those exact weights transiently, then run the existing license-cleared
host suite against the resulting float artifact, capturing text plus segment
timing. Only if the exported float artifact is numerically sane should a
Q8/Q5 Android candidate be measured on a physical arm64 device. The attached
emulator can check loading and application integration only; it cannot qualify
physical memory, latency, or accent accuracy.

`tools/eval_v6_android_stt_export.py` is the aggregate-only host evaluator for
that step. It holds reference/hypothesis text in memory, reports only WER,
runtime, duration, and aggregate edit counts, and refuses a short frozen slice.
Its report includes model and source-manifest hashes; any decode failure now
leaves an aggregate failure report and exits nonzero, so a partial suite cannot
be mistaken for a valid WER result. Model hashing is streamed to keep memory
bounded for large Whisper artifacts.

## Reproducible candidate exporter — 2026-10-02

`tools/export_v6_stt_android.py` now merges the exact evaluated PEFT adapter
into its HF Whisper base and packages it into a float16 GGML artifact plus an
Android-slot Q5_0 artifact. It verifies that every supplied passing
qualification report names the same base and adapter hashes, checks the
tokenizer ID map against `config.vocab_size`, and requires distinct passing
`vocab-heldout` and `ami-dev` suite reports (suite IDs are emitted by the paired
comparison pipeline). It stages converter compatibility files without
modifying the source, and requires clean source checkouts at the
previously exercised whisper.cpp converter revision
`a44e07845931421bb6f3447ce0010ed9dc76a118` and OpenAI Whisper mel-filter
revision `86098128c0b4f24f0e2aa2994de830614b474227`. Artifacts and a hash
manifest are written atomically outside Git; conversion output never contains
audio, references, or hypotheses.

The export script has unit coverage for tokenizer IDs, full-checkpoint
requirements, report/hash binding, and failed qualification reports. Its
tokenizer preflight was checked against the existing fused V5 Whisper
checkpoint: 50,258 BPE tokens plus added tokens resolve to exactly 51,865 IDs,
matching the checkpoint configuration. The script has **not** been run on the
active V6 candidate; its merge, conversion, and quantization remain gated on
passing all paired STT evaluations.
Even a successful export is only a host artifact candidate, not proof of
Android WER, metadata parity, memory, or latency.
