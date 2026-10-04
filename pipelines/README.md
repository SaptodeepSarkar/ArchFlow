# Reproducible model pipelines

`pipelines/` is the stable entry point for adding data, training, and checking
models.  The existing scripts in `tools/` remain the implementation library;
they are deliberately not moved because current experiment records and
automation refer to them.

The shared, non-Git data contract is [`../data/shared/README.md`](../data/shared/README.md).
It separates STT material (audio/manifests/evaluation) from formatter material
(raw hypotheses, references, review, and prepared rows).  Model weights, audio,
private feedback, caches, and generated datasets stay out of Git.

## Build targets

```sh
make desktop-debug       # Linux daemon, CLI, QML desktop app
make android-debug       # android/app/build/outputs/apk/debug/app-debug.apk
make android-release     # unsigned release APK; sign before public distribution
make install-desktop     # local Linux/QML installation after a release build
```

## Data and training

1. Put a licensed dataset and its provenance record in the appropriate
   `data/shared/{stt,llm}/` lane.  Do not add audio or weights to Git.
2. Create a manifest that uses paths relative to the manifest whenever possible.
3. Run `make data-check` before a training run.
4. Run one of the wrappers below. They pass only paths and options to the
   existing trainers; audio and transcripts are never printed or passed as text
   arguments.

```sh
make train-stt ARGS="--manifest data/shared/stt/manifests/train.jsonl --model /path/to/checkpoint --out /path/to/run"
make train-formatter ARGS="--model /path/to/base --out /path/to/run --correction-file data/shared/llm/prepared/corrections.jsonl"
```

The wrappers are intentionally narrow. Add a new trainer behind a new wrapper
only after documenting its input schema, provenance requirements, evaluation,
and export target here.

## V6 formatter qualification

`formatter/evaluate-v6-seq2seq-all.sh --help` describes the separate paired
evaluation entry point. It runs V5 and V6 on the diagnostic challenge, hard
evaluation, mixed heldout, real heldout, and independent challenge suites.
An early failure does not skip later suites; any execution or gate failure
still makes the entire command fail. Output must be a new directory outside
the repository. The updated evaluator records row-level guard coverage.

The independent challenge must be frozen, excluded from training and replay,
and not used to choose this candidate. Supplying a path alone does not prove
that independence: verify its provenance and source overlap before running.
Previously inspected diagnostic suites remain useful regression tests, but
are insufficient alone for promotion. A green formatter evaluation is not
an STT or Android memory/latency qualification.
