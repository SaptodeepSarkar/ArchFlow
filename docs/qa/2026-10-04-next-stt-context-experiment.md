# Next STT context-diversity experiment — preregistered, not started

## Hypothesis

The rejected 20% vocabulary-exposure candidate improved synthetic vocabulary
WER but achieved only 135/162 protected-term occurrences (83.33%), below the
99% gate, and regressed protected terms on real meeting suites. Increasing
sentence-context diversity may improve robustness beyond memorizing three
sentence frames. This is a hypothesis, not a demonstrated cause or result.

## Controlled change and data

Expand the same 79 terms and two US Kokoro voices from three to twelve
sentence contexts. Require all 1,896 clips and validated provenance/checksums.
Use the canonical preparation wrapper with the prior 20% experiment's
`vocab-split/heldout.jsonl` frozen. Keep both voices of previously heldout
contexts out of training. Report the actual split counts, not nominal 20%
counts: frozen contexts can increase the holdout size.

Retain the clean Whisper-small initialization, AMI training source, 1,500
steps, batch 2, accumulation 8, learning rate 1e-5, seed, augmentation setting,
and 20% vocabulary-source draw probability from the recorded control. Verify
the previous run manifest before launching, rather than infer unstated flags.
Do not initialize from a rejected or Flux-derived adapter. Keep ICSI dev
evaluation-only and ICSI test untouched for selection.

At 1,500 steps × 2 × 8, nominal exposure is 24,000 examples, including about
4,800 vocabulary draws. More distinct clips therefore means fewer repeats per
clip; it is not a same-repeat-count experiment. Audit the realized sampler
and per-source counts before training. Two synthetic US voices do not prove
Indian-English/Hinglish or unseen-speaker generalization.

## Budget and abort conditions

Recipe correction discovered after preregistration: the canonical custom
weighted loss now explicitly enables proper gradient-accumulation scaling
under the installed Transformers version. First establish a three-context
clean-base control under that same corrected trainer before attributing an
expanded-context difference to data diversity. The old 20% candidate remains
historical, not a matched causal control. See
`2026-10-04-stt-accumulation-loss.md` for the executable regression evidence.

GPU training starts only after the formatter releases the GPU. Use resumable
45-minute segments, at most 5 GiB host memory, no scope swap, bounded workers,
and the local 6 GiB GPU. Do not increase limits to mask an OOM. Abort on CUDA
OOM, memory-limit termination, incomplete/corrupt pack, heldout leakage,
changed resume inputs, or invalid provenance. No automatic runtime promotion.

## Evaluation and decision

Evaluate paired clean-base/control and candidate vocabulary-context, AMI dev,
and ICSI dev suites, then compare with the archived V5 production recognizer
on admissible common audio. Report WER, protected-term support/accuracy,
generation runtime, and raw versus contextual-bias results separately. Reject
protected-term regressions or failure of the 99% vocabulary gate, even if WER
improves. This experiment cannot alone qualify mobile deployment: conversion
sanity, quantization robustness, preserved timestamps, Android peak PSS/RSS,
and Android latency remain separate requirements.
