# Vaani documentation

Start here when working on or installing the project. The repository keeps
runtime documentation, environment decisions, and experiment records separate
so benchmark notes do not get confused with user-facing setup instructions.

## Use Vaani

- [Installation and operation](INSTALL.md) — dependencies, setup, shortcuts,
  runtime flow, and diagnostics.
- [Configuration](configuration.md) — supported keys and policy tradeoffs.
- [Compatibility](compatibility.md) — tested environments and known limits.
- [Troubleshooting](troubleshooting.md) — common failures and safe recovery.
- [Manual checks](manual-checks.md) — laptop checks that still need a human.

## Understand Vaani

- [Architecture](architecture.md) — daemon, worker, UI, and insertion flow.
- [Environment ADR](ADR-001-environment.md) — verified host versions and API
  decisions; do not infer versions from memory.
- [Performance](performance.md) — measured latency and resource notes.

## Models and experiments

- [V5 benchmark](v5-benchmark.md) — frozen STT and formatter evaluation.
- [V6 baseline](V6_BASELINE.md) — source-grounded formatter control and gates.
- [V6 dataset audit](V6_DATASET_AUDIT.md) — license/access decisions before
  corpus ingestion.
- [V6 dataset status](V6_DATASET_STATUS.md) — actual data counts and next
  evidence gate; not a model-completion claim.
- [V6 data experiment log](V6_EXPERIMENT_LOG.md) — bounded real-derived pilot
  configuration and results.
- [V6 review protocol](V6_REVIEW_PROTOCOL.md) — required approval criteria for
  real-derived and synthetic candidate targets.
- [V6 Android V5 portability](V6_ANDROID_V5_PORTABILITY.md) — bounded export
  investigation; no Android replacement claim.
- [V6 formatter benchmark](v6-formatter-benchmark.html) — case-level report.
- [Model training status](model-training-status.html) — evidence dashboard.
- [Model efficiency roadmap](model-efficiency-and-quality-roadmap.md) — open
  research directions, not runtime guarantees.

The remaining `v5-*`, `v6-*`, and long-form research files are retained as
experiment records. They are not installation requirements and should not be
treated as claims about the default runtime.

## Android

Android-specific UX specifications, reports, and benchmark notes live under
[`../android/docs/`](../android/docs/). The Android client is a separate
`InputMethodService`; it does not connect to the Linux daemon socket.

## Developer tooling

Graphify keeps a local, AST-derived code map in `graphify-out/`. It refreshes
on committed changes and branch switches through synchronous Git hooks. Use
`graphify query "question"`, `graphify path "A" "B"`, or `graphify explain
"symbol"` to inspect it; run `graphify extract . --code-only --cargo` to
rebuild from scratch. The generated output is local and intentionally ignored
by Git.
