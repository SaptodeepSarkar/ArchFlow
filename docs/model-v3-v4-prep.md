# v3 STT and v4 LLM preparation

This document turns `WhisperFlow_Mobile_STT_and_Text_Intelligence_Report.md`
into the next controlled experiment. No candidate is promoted by benchmark
claims alone.

## Decision

### v3 STT

Keep `cozy_stt_public_indian_v2` as the control. It is already measured on the
Indian-English split and its runtime is integrated with ArchFlow. Do not throw
away that result or train a new Whisper model from scratch.

Prepare two comparisons:

1. **Whisper-small adaptation (internal v3):** continue the current public Indian-English
   recipe, adding only verified hard-term audio, real pronunciation variants,
   noise/gain augmentation, and a speaker/session-held-out test set.
2. **Streaming challenger:** evaluate a small streaming Conformer/Transducer
   model before fine-tuning it. The report's architecture recommendation is
   technically sound for mobile latency, but a new architecture is only useful
   if it beats v2 on word error, critical terms, CPU real-time factor, and
   memory. Use Moonshine Tiny only as a small **English batch-ASR CPU
   baseline**. Its documented architecture is sequence-to-sequence, so it
   should not be described as the streaming/partial-transcript challenger.
   The real challenger must be a checkpoint explicitly trained for streaming
   Conformer/Transducer inference. Sherpa-ONNX is a deployment runtime, not a
   model family; select a compatible streaming checkpoint first, then verify
   its export and runtime behaviour. NeMo's cache-aware streaming
   FastConformer/Transducer family is a valid research source, but it still
   must be benchmarked on the target runtime and hardware.

The challenger must pass the same audio manifest and must include `HTML`,
`CSS`, `narcotics`, `acrobat`, `Celsius`, `MCP`, `CTC`, medical terms, names,
numbers, and Indian-English pronunciation variants. Until that comparison is
complete, Whisper v2 remains the production test model.

### v4 LLM

Do not make v4 a larger free-form chatbot. Test two paths against the same
contract dataset:

- **Qwen3-0.6B control:** v3 adapter plus a structured v4 training stage.
- **Compact challenger:** SmolLM2-360M-Instruct, adapted only if its
  tokenizer/runtime and output quality are practical on the target phone.
  It is primarily English, so it is an English-only efficiency comparison—not
  a substitute for Qwen on Indian-English code-switching without measured
  evidence. MobileLLM-350M is a research architecture and paper benchmark,
  not a named drop-in checkpoint in this experiment; use its design findings
  as background, not as an install target.

Qwen3-0.6B remains the first v4 candidate because it is already downloaded,
multilingual, and integrated. The v3 result was limited by sparse intent data
and free-form text targets, not by a proven base-model capacity limit. A new
LLM must beat Qwen3 on protected-span preservation and intent accuracy before
it is worth the deployment work.

## v4 text contract

The editor should receive transcript text as untrusted data. It must return a
validated record, not an unconstrained answer:

```json
{
  "operation": "punctuate",
  "result": "Can you open the browser?",
  "changed_spans": [],
  "needs_confirmation": false
}
```

Allowed operations are `preserve`, `punctuate`, `grammar`, `make_list`,
`numbered_list`, `emoji`, and `format_only`. `execute`, `browse`, `send`, and
other actions are not valid cleanup operations. Spoken commands remain text to
format; ArchFlow's action layer is separate.

Every v4 example must label:

- operation and punctuation intent;
- list style and whether spoken items exist;
- explicit emoji versus the word “emoji” as ordinary text;
- protected spans: names, acronyms, technical/medical words, numbers, units,
  code, paths, URLs, and negation;
- disfluency, uncertainty, and Indian-English code-switching;
- whether a confirmation is required.

## Required benchmark slices

### STT

- clean Indian English;
- Indian English with realistic gain/noise variation;
- hard lexical terms and acronyms;
- medical/scientific terms;
- numbers, dates, units, URLs, paths, and code;
- hesitation, word-finding difficulty, false starts, and repeated words;
- speaker/session-held-out clips.

Report WER, deletion rate, critical-token exact match, p50/p95 final latency,
time-to-first-partial, peak RAM/VRAM, CPU real-time factor, and model size.

### LLM

- punctuation questions and exclamations;
- grammar with no semantic rewrite;
- prose versus actual lists;
- numbered and dotted lists;
- explicit emoji requests;
- hard-term preservation: `HTML`, `CSS`, `narcotics`, `acrobat`, `MCP`,
  `CTC`, `Celsius`, and user vocabulary;
- spoken commands formatted as text, never executed;
- “do not make a list” and “keep the exact wording” adversarial cases;
- malformed-output and protected-span rejection tests.

Pass criteria are zero invalid applied records, no unsupported content, and no
regression in the existing structure suite. Exact string match is secondary.

## Experiment order

1. Freeze v2 STT and current LLM as controls.
2. Create the speaker/session-held-out STT hard-term suite.
3. Benchmark the streaming challenger without fine-tuning.
4. Build the v4 structured contract dataset and validator.
5. Fine-tune Qwen3-0.6B as `llm-v4-qwen`.
6. Evaluate the compact challenger only if the Qwen control cannot meet the
   mobile memory/latency budget.
7. Deploy only a candidate that wins on the complete scorecard.

## Current status

- v2 STT is active in ArchFlow.
- The previous v3 LLM adapters remain isolated and are not deployed.
- v4 preparation is specification and benchmark work; no new model is being
  silently installed.

## Research basis

- [Moonshine Tiny model card](https://huggingface.co/moonshine-ai/moonshine-tiny)
  describes a 27M, English-only sequence-to-sequence ASR model for constrained
  on-device use. Its limitations explicitly include possible hallucination and
  repetition on short or clipped audio; it is therefore a batch baseline, not
  evidence of safe streaming performance.
- [NVIDIA NeMo featured ASR models](https://docs.nvidia.com/nemo/speech/nightly/asr/featured_models.html)
  documents FastConformer CTC/RNN-T/TDT families, 110M edge checkpoints, and
  cache-aware streaming Conformer configurations. The documentation does not
  itself establish mobile runtime performance, so that remains a benchmark
  requirement.
- [Qwen3-0.6B model card](https://huggingface.co/Qwen/Qwen3-0.6B) documents its
  0.6B size, 100+ language/dialect support, and a non-thinking mode intended
  for more efficient generation. That source is a capability claim, not proof
  that it will preserve technical spans or follow this JSON contract.
- [SmolLM2-360M-Instruct model card](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct)
  identifies the model as 360M and primarily English; its stated limitations
  require evaluation rather than assuming factual or formatting reliability.
- [MobileLLM paper](https://arxiv.org/abs/2402.14905) is retained as a
  sub-billion mobile architecture comparison, not a promise that a smaller
  generic model will automatically format transcripts better or a reference to
  a ready-to-deploy checkpoint.

Sources checked 2026-09-13. Claims about the existing ArchFlow integration,
the current v2/v3 results, and downloaded local models are internal project
state; they are intentionally not presented as externally sourced facts.
