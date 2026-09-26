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
- Fine-tuning, quantization, or a different Whisper architecture is not
  authorized by this document until the dataset's human-review gate is met.

## Immediate next experiment

Run the frozen fused-checkpoint export through the existing 100-clip
license-cleared suite on host first, capturing text plus segment timing. Only
if the exported float artifact is numerically sane should a Q8/Q5 Android
candidate be made and measured on physical hardware.

`tools/eval_v6_android_stt_export.py` is the aggregate-only host evaluator for
that step. It holds reference/hypothesis text in memory, reports only WER,
runtime, duration, and aggregate edit counts, and refuses a short frozen slice.
