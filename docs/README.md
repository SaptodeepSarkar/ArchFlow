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
- [Bug audit](bug-audit-2026-09-11.md) — historical fixes and remaining limits.

## Models and experiments

- [V5 benchmark](v5-benchmark.md) — frozen STT and formatter evaluation.
- [V6 baseline](V6_BASELINE.md) — source-grounded formatter control and gates.
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
