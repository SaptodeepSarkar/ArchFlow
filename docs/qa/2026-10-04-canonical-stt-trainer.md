# Canonical shared Whisper trainer safeguards

Reviewed and integrated the local V6 entry point and shared trainer changes:
pre-split manifests, repeated SQLite sources, explicit source draw fractions,
LoRA initialization/resume options, streaming feature preparation, disabled
augmentation controls, and the Whisper EOS-label fix. Genuine EOS labels
must survive batch padding even when the tokenizer uses EOS as its pad ID.

Additional corrections reject nonfinite/nonpositive sample weights before
feature padding and avoid constructing an evaluation dataset from `None`
when a pre-split nonstreaming run has no evaluation rows. Streaming remains
the intended bounded-memory path for full-corpus training.

The source-sampling audit reads only counts and term hashes. Its `--steps`
argument counts example draws, not optimizer updates: 1,500 updates with
batch 2 and accumulation 8 means 24,000 nominal draws on this single-GPU
recipe. It estimates expected exposure, not observed sampler coverage.

Ten focused tests passed, including genuine EOS retention, invalid weights,
seeded source sampling with a real-source remainder, exposure estimates,
and split integrity. No weights were loaded or training started by these
tests. They do not verify resume equivalence, corpus licensing, WER, or
Android performance. A hashed experiment manifest and smoke run are still
required before the next long STT training job.

The live formatter and synthesis sources were not modified. The original
dirty checkout remains preserved; only the reviewed STT files were integrated
into the main integration checkout.
