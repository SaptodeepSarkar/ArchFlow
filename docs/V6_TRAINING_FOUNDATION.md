# V6 training foundation from the local research set

Status: research synthesis and experiment policy; not a model-quality claim.
Updated: 2026-10-04.

## Purpose and evidence boundary

This document turns the papers in [`Research/`](Research/) into testable
choices for Vaani V6. The directory contains 33 PDFs and 31 distinct works:
GPT-4o System Card is present twice and DeepSeek-R1 is present in both the
alignment and small-model folders. The papers span data curation, speech
recognition, model adaptation/efficiency, alignment, and evaluation. System
cards and large-model technical reports are useful for process/evaluation
lessons, but their compute scale and undisclosed data do not establish a recipe
for Vaani's small local models.

The source papers are primary research reports; their findings are evidence to
test, not guarantees that transfer to our corpus, model, or hardware. In
particular, leaderboard results, synthetic-label quality, reward-model scores,
training loss, step count, and host GPU throughput are not release gates.

## Conclusions that change the V6 workflow

1. **Start from the deployed base model; adapt narrowly.** V6 is task/domain
   adaptation, not foundation-model pretraining. The LoRA and QLoRA results
   support frozen-base low-rank adaptation as a practical, reversible
   experiment. They do not imply that a chosen rank, learning rate, or
   quantization level is correct for Vaani. For each candidate, record the
   exact base revision, tokenizer, adapter settings, data manifest, code
   revision, seed, and checkpoint-selection rule.
2. **Data quality and split design outrank raw row count.** Whisper, Dolma,
   FineWeb, and the deduplication study all document the importance of filtering,
   near-deduplication, provenance, and contamination checks. Make splits by
   underlying utterance/base, speaker or meeting, source, and template family
   as appropriate *before* augmentation. A thousand correlated variants are
   not a thousand independent speakers or intents.
3. **Treat synthetic data as a labeled coverage instrument, not truth.**
   Synthetic data can efficiently cover rare phenomena (Canary, Nemotron, and
   the large audio reports demonstrate uses of generated/pseudo-labeled data),
   but its labeler and distribution are part of the data provenance. Keep
   synthetic and real-derived results separate; reject unsupported teacher
   rewrites; keep an untouched real-speaker/source evaluation. Never use a
   synthetic-only win as evidence of real-world accuracy.
4. **Choose mixtures deliberately and measure slices.** DoReMi, Canary, and
   Canary/Parakeet show that mixture weights, source/language balance, duration
   bucketing, and staged fine-tuning affect outcomes. Report per-source,
   language/accent, phenomenon, duration, and noise slices, not only a pooled
   score. Change one sampling or optimization factor per controlled comparison.
5. **A low training loss is not a successful formatter.** V6's objective is
   faithful speech formatting. Preserve the existing ordering
   `meaning > intent > uncertainty/emotion > clarity > requested structure >
   grammar > punctuation/capitalization > brevity`. A candidate that is fluent
   but changes negation, numbers, claims, uncertainty, quoted commands, or
   speaker register fails regardless of loss or exact-match improvements on
   generated templates.
6. **Do not optimize against a weak proxy without an independent check.**
   DPO/constitutional/RL papers show how preference signals can steer behavior;
   reward-overoptimization work shows that maximizing an imperfect learned
   proxy can worsen the true objective. For V6, exact match, automatic semantic
   metrics, and LLM-as-judge are diagnostics. They must be paired with
   source-grounded invariants, adversarial contrasts, and a frozen independently
   authored challenge set. Preference/RL training is not the next step for a
   constrained formatter.
7. **Benchmark the deployed path and its resource budget.** Whisper, Canary,
   FastConformer, and Kimi-Audio all underscore that decoding configuration,
   normalization, timestamps, and latency affect reported results. Evaluate
   with the actual Linux/Android runtime, tokenizer, quantization, and decode
   settings. Do not infer Android RAM, latency, or accuracy from the laptop.

## V6-specific training design

### Formatter / LLM

- **Keep V5 and deterministic safety behavior as frozen controls.** Compare a
  copy-biased constrained seq2seq formatter, source-grounded edit tagging with
  deterministic rendering, and a hybrid (deterministic high-confidence
  mechanical edits plus a learned semantic-repair component). The papers do
  not justify choosing a free-form generator by default.
- **Build data around contrasts, not just phenomena.** Include paired examples
  where similar surface wording means either a repair or narration/quotation;
  incidental versus meaningful hesitation; accidental versus emphatic
  repetition; explicit list request versus ordinary prose; list continuation
  versus return to prose; correct pass-through versus spelling normalization;
  and code-switching/name/technical-token preservation.
- **Use strict source-to-target checks.** Preserve protected spans and compare
  the target against the current utterance only. Reject additions that rely on
  world knowledge. Ambiguous edits should keep the source or be excluded.
  Teacher-generated labels remain proposals until deterministic checks and
  independent evaluation support them.
- **Split by source lineage.** Keep all augmentations of a base in one split.
  Exclude challenge and hard-evaluation sources from training, replay, prompt
  construction, and checkpoint selection. Maintain one frozen final test not
  repeatedly inspected during recipe tuning.
- **Predeclare the checkpoint rule.** The current constrained seq2seq pipeline
  uses a fixed final step; dev loss is logged as a diagnostic, not used to pick
  the release checkpoint. If later experiments compare checkpoints, selection
  must use a predeclared dev tuple and still pass independent hard gates. At
  minimum report exact output, normalized exact,
  source-token preservation/deletion, unsupported additions, protected-span
  recall, negation/number preservation, punctuation, structure/list behavior,
  speech-act/emotion preservation, and per-slice scores. The worst safety slice
  is a veto, not something a pooled average can hide.
- **Run a small, safe smoke first**, then a bounded candidate with a fixed
  stopping rule. Save resumable checkpoints and machine-readable aggregate
  metrics; do not silently restart or change the data mixture mid-run.

### STT

- **Do not confuse vocabulary exposure with an acoustic vocabulary extension.**
  Keep Whisper's tokenizer/model interface unchanged unless an export and
  decoder change is deliberately designed. Test contextual biasing separately
  from acoustic fine-tuning. A “known word” score must use unseen sentence
  contexts and real held-out speakers/sources.
- **Initialize every candidate from the clean, admissible Whisper checkpoint.**
  Do not continue from a candidate with questionable data lineage. Train and
  evaluate using the target inference backend/configuration; keep each source's
  license, transcript style, accent/language, split unit, duration, and
  synthetic/real status in the manifest.
- **Balance and qualify the data mix.** Use real spontaneous speech and
  accent-relevant data where terms permit; use licensed synthetic speech only
  as a tagged supplement. Do not let one prolific speaker or synthetic voice
  dominate. Include speech/no-speech and acoustic variation only when labels
  and deployment purpose support them.
- **Pair general ASR and vocabulary metrics.** Report normalized WER and CER,
  exact/protected-term accuracy, deletion/insertion/substitution breakdown,
  language/code-switch and accent slices, and long/short/noisy audio slices.
  Improvements on the target vocabulary cannot offset a material broad WER or
  protected-content regression. Keep AMI/ICSI and held-out Common Voice roles
  distinct; never tune on final test speakers.
- **Qualify portability after model quality.** For Android, verify conversion
  numerically on fixed audio, WER/CER and Indian-English/Hinglish behavior,
  timestamps/metadata, peak device memory, and end-of-utterance latency. A
  successful CTranslate2 run does not establish whisper.cpp compatibility.

## Experiment protocol (required before unpausing training)

1. Freeze a versioned task contract, source inventory/licenses, base checkpoint
   hashes, and train/dev/final-test manifests. Hash manifests; scan exact and
   near duplicates; prove split disjointness at the true independent unit.
2. Publish a one-page preregistration for the next comparison: hypothesis,
   one changed factor, primary metric, safety vetoes, fixed evaluation command,
   compute/time cap, checkpoint selection, and stop condition.
3. Run data/schema/provenance validation and a tiny overfit/smoke test. The
   smoke establishes that the code and loss can learn the intended mapping; it
   is not a quality result.
4. Train a single candidate from the frozen base. Track train/dev curves,
   source and phenomenon mix, learning rate, gradient/overflow status, peak
   memory, throughput, and checkpoint hashes. Stop for divergence, resource
   guard, or a predeclared plateau; do not infer quality from steps completed.
5. Evaluate the same frozen inputs/config for the candidate and control, using
   aggregate-only reports. Select on dev, use hard suites as vetoes, and reserve
   the final held-out test for a one-time qualification after recipe selection.
6. Promote only if every safety/accuracy gate passes and the real target device
   meets its latency/memory budget. Otherwise quarantine the artifact, preserve
   its evidence, and revise one hypothesis at a time.

## Paper coverage and transfer notes

The following inventory records the role of every distinct work in the local
set. Duplicate file copies are listed once here. Local PDFs are linked so the
evidence can be reopened directly.

### Data and speech

- [Dolma](Research/Data-Curation/C1_Dolma_AI2_2024_2402.00159.pdf): transparent
  corpus construction, filters, deduplication, source documentation, and
  responsible data release.
- [FineWeb](Research/Data-Curation/C2_FineWeb_HF_2024_2406.17557.pdf): explicit
  curation ablations; quality filters and educational-data selection need
  measured comparisons rather than intuition.
- [Deduplicating Training Data](Research/Data-Curation/C3_Dedup_Google-Stanford_2021_2107.06499.pdf):
  near duplicates cause memorization and train/test contamination; deduplication
  can improve quality while reducing redundant compute.
- [DoReMi](Research/Data-Curation/C4_DoReMi_Stanford-Google_2023_2305.10429.pdf):
  a smaller proxy can inform domain mixture weights; mixture tuning is a
  measurable optimization problem, not a row-count guess.
- [Whisper](Research/STT/A1_Whisper_OpenAI_2022_2212.04356.pdf): broad,
  diverse weak supervision, transcript-quality filtering, fuzzy deduplication,
  train/eval contamination checks, multitask tokens, and full training details;
  also warns that narrow fine-tuning can learn brittle dataset cues.
- [Conformer](Research/STT/A2_Conformer_Google_2020_2005.08100.pdf): local
  convolution plus global attention is an acoustic architecture finding, not a
  reason to replace Vaani's existing Whisper model during this data-focused
  iteration.
- [FastConformer](Research/STT/A3_FastConformer_NVIDIA_2023_2305.05084.pdf):
  aggressive downsampling and local attention reduce cost; long-form support
  required explicit context fine-tuning and long-audio tests.
- [Canary](Research/STT/A4_Canary_NVIDIA_2024_2406.19674.pdf): shows data
  efficiency can come from architecture plus synthetic translation data,
  balancing, dynamic blending/bucketing, and noise-robust fine-tuning—not
  synthetic volume alone.
- [Canary-v2 / Parakeet-v3](Research/STT/A5_Canary-Parakeet_NVIDIA_2025_2509.14128.pdf):
  staged pretraining/fine-tuning, dynamic balance over large multilingual data,
  explicit non-speech training, and a separate aligner for timestamps; its
  1.7M-hour setting is not transferable as a small-corpus recipe.
- [Kimi-Audio](Research/STT/A6_Kimi-Audio_Moonshot_2025_2504.18425.pdf):
  extensive audio cleaning/segmentation/pseudo-labeling, staged audio/text
  pretraining and SFT, and an evaluation toolkit addressing normalization and
  inference-config variance. Scale is far beyond Vaani; pipeline discipline
  and evaluation lessons are relevant.

### Adaptation, scale, and efficiency

- [Scaling Laws](Research/Small-LLM/B1_ScalingLaws_OpenAI_2020_2001.08361.pdf):
  data, model, and compute interact; avoid assuming “train to convergence” or
  that adding steps/data always pays off.
- [Constitutional AI](Research/Small-LLM/B2_ConstitutionalAI_Anthropic_2022_2212.08073.pdf):
  self-critique and AI preference labels are a staged proposal/feedback method;
  they depend on the quality of principles and evaluator.
- [Claude 3 Model Card](Research/Small-LLM/B3_Claude3_ModelCard_Anthropic_2024.pdf):
  training-process transparency and broad capability/safety evaluation are
  important; proprietary process details limit recipe transfer.
- [DeepSeek-V2](Research/Small-LLM/B4_DeepSeek-V2_2024_2405.04434.pdf):
  MoE/attention innovations optimize very large-model compute and serving;
  irrelevant to changing Vaani architecture absent a measured deployment need.
- [Nemotron-4](Research/Small-LLM/B5_Nemotron4-340B_NVIDIA_2024_2406.11704.pdf):
  large synthetic alignment corpora can be effective when generated and
  filtered as a deliberate pipeline; does not make unverified synthetic labels
  ground truth.
- [Minitron](Research/Small-LLM/B6_Minitron-Pruning-Distill_NVIDIA_2024_2407.14679.pdf):
  pruning plus distillation can be a compute-efficient route to smaller models,
  but only if compression is a goal and target-device quality is measured.
- [DeepSeek-V3](Research/Small-LLM/B7_DeepSeek-V3_2024_2412.19437.pdf):
  documents stable large-scale pretraining plus SFT/RL and systems choices;
  useful for reproducibility discipline, not a small-model recipe.
- [DeepSeek-R1](Research/Alignment/D3_DeepSeek-R1_2025_2501.12948.pdf):
  verifiable-reward RL can elicit reasoning on math/code tasks; that reward
  structure is absent for faithful speech cleanup, so it is not a justified V6
  method. The duplicate is `Small-LLM/B8`.
- [Kimi K2](Research/Small-LLM/B9_Kimi-K2_Moonshot_2025_2507.20534.pdf):
  staged synthetic data and environment-based RL at frontier scale; its
  sophisticated verifiable agentic rewards do not transfer to intent
  preservation without equivalent objective labels.
- [GPT-4o System Card](Research/Small-LLM/B10b_GPT-4o-SystemCard_Official_OpenAI_2024.pdf):
  broad multimodal training and system-level safety/evaluation disclosure; not
  a reproducible small-model fine-tuning recipe. `B10` is a duplicate copy.
- [LoRA](Research/Efficiency/E1_LoRA_Microsoft_2021_2106.09685.pdf): freeze the
  pretrained model and learn low-rank updates; compare adapters against the
  unchanged baseline and retain reversible artifacts.
- [QLoRA](Research/Efficiency/E2_QLoRA_UW_2023_2305.14314.pdf): low-bit base
  weights plus LoRA can reduce training memory; quantization and paged
  optimizers are engineering choices to benchmark, not accuracy guarantees.
- [FlashAttention](Research/Efficiency/E3_FlashAttention_Stanford_2022_2205.14135.pdf):
  memory-IO-aware exact attention can improve training speed/context without
  approximating the attention computation; optimize runtime after correctness
  and quality are instrumented.
- [Speculative Decoding](Research/Efficiency/E4_SpeculativeDecoding_Google_2022_2211.17192.pdf):
  an inference acceleration with an exact sampling guarantee under its method;
  it does not train or improve the formatter and is outside the current blocker.

### Alignment and evaluation

- [InstructGPT](Research/Alignment/D1_InstructGPT_OpenAI_2022_2203.02155.pdf):
  demonstrates staged SFT → preference model → PPO, and reports regressions
  that motivate mixing pretraining data back in. It requires human preference
  infrastructure and does not establish that RL is appropriate for V6.
- [DPO](Research/Alignment/D2_DPO_Stanford_2023_2305.18290.pdf): direct
  preference optimization can avoid a separate RL loop, but still optimizes a
  preference dataset; it cannot repair ambiguous or ungrounded labels.
- [Reward Overoptimization](Research/Alignment/D4_RewardOveropt_OpenAI_2022_2210.10760.pdf):
  increasing optimization against an imperfect proxy can reduce true reward;
  cap optimization and validate against independent gold evidence.
- [HELM](Research/Evaluation/F1_HELM_Stanford_2022_2211.09110.pdf): evaluate
  across scenarios and multiple desiderata; publish missing coverage, not one
  aggregate score.
- [TruthfulQA](Research/Evaluation/F2_TruthfulQA_Oxford-OpenAI_2021_2109.07958.pdf):
  more scale does not guarantee truthful behavior; include contrastive cases
  where copying versus correction is the distinction.
- [BERTScore](Research/Evaluation/F3_BERTScore_Cornell_2019_1904.09675.pdf):
  contextual similarity can complement exact overlap for semantic evaluation,
  but it does not enforce preservation of numbers, negation, entities, or tone.
- [MT-Bench / LLM Judge](Research/Evaluation/F4_MTBench-Berkeley_2023_2306.05685.pdf):
  strong LLM judges can scale preference evaluation but show position,
  verbosity, self-enhancement, and reasoning biases; pair with blinded human or
  deterministic checks.

## Immediate decision

Training and synthetic audio generation remain paused at the user's request;
the research synthesis and non-training preflight are complete, but this does
not resume either process. The current evidence supports a controlled gate:
prior V6 STT adapters regressed protected vocabulary on
held-out audio; prior formatter models showed large generalization gaps between
template/grouped tests and independent challenges; and a recent trainer run had
a replay-argument parsing defect. Resume only after the affected data/CLI
contracts are fixed, a single next experiment is preregistered under the rules
above, and its control/challenge suites are frozen. The corrected formatter
preflight now proves all planned replay sources enter the training stream,
excludes exact sources found in final test inputs, and records data/model/code
fingerprints without transcript content. It also showed the currently paused
run admitted three foundation examples that overlap those final tests; that
run is quarantined. See
[`V6_DATASET_STATUS.md`](V6_DATASET_STATUS.md),
[`V6_STT_TRAINING.md`](V6_STT_TRAINING.md), and
[`V6_BASELINE.md`](V6_BASELINE.md) for the underlying run evidence.
