# Vaani repository audit

Date: 2026-09-16

## Scope and evidence

This is a source-tree audit of commit `9b1c581d` (`fix(android): distinguish enabled and selected IMEs`). Evidence came from `git ls-files`, `git status --short --ignored`, Cargo metadata/tree, the Android Gradle sources, and the existing documentation. Runtime checks were repeated on 2026-09-16 with the local Gradle 8.9 distribution and `emulator-5554`.

## Current shape

| Area | Current state | Classification |
|---|---|---|
| Shared core | Rust crates for protocol, state, VAD, segmentation, reconciliation, config, and transcript cleanup | KEEP; extend with stable contracts |
| Linux controller | `vaanid` owns capture, focus, clipboard, insertion, worker supervision, and Quickshell events; `vaani-desktop` now owns portable lifecycle plus Linux adapter foundations | KEEP for Linux; connect native shell/audio adapters |
| CLI/worker | Rust CLI and worker; whisper.cpp and faster-whisper adapters | KEEP; put behind registry/engine interfaces |
| Android | Native Kotlin Activity plus `InputMethodService`, Android `SpeechRecognizer` backend | KEEP; refactor into explicit repositories/pipeline |
| Linux UI | Quickshell/QML overlay and settings | KEEP for Linux overlay; do not make it the cross-platform UI |
| Windows | Target-specific User32 global-hotkey adapter foundation; no complete shell/audio/insertion client | BUILD as a separate native shell |
| Personalization | Portable deterministic rules, bounded Android SQLite store/UI with legacy migration, dependency-free JSONL repository, and desktop repository writes exist; Linux imports/renders persisted records | EXTEND with platform settings UI and migrations |
| Sync/auth | Local sync records/repository, Firestore rules/emulator tests, and Android optional auth/provider bridge exist; production provider enablement and desktop adapters remain | EXTEND after local-first data model |
| Models | Manifest plus user-local V5/cozy references; no model weights tracked | KEEP policy; formalize package validation |
| Training | Historical V1–V5/V6 scripts, ignored datasets, checkpoints, and caches | ARCHIVE/document; exclude from active runtime |
| Tests | 73 passing Rust tests plus one ignored hardware test, 6 Android policy/reducer tests, 3 connected Android tests, and 11 portable desktop tests; no native desktop test suite | KEEP coverage; ADD platform and contract tests |

## Keep / refactor / replace / archive / delete

### Keep

- `crates/vaani-core/` state machine, protocol, VAD, segment/reconcile and safety-oriented transcript tests.
- Linux capture/insertion supervision and the Quickshell event protocol while the Linux shell is retained.
- Android native IME and short onboarding flow as the platform-specific shell.
- Historical benchmark and training documentation that explains measured decisions.
- Model manifests and setup scripts that keep weights out of Git.

### Refactor

- Move STT, formatter, personalization, insertion, storage, and metrics boundaries into explicit contracts.
- Replace Android `SharedPreferences` product data with a local repository/database abstraction.
- Separate Linux-specific insertion from portable insertion outcomes and recovery semantics.
- Turn model resolution into manifest discovery, validation, capability reporting, and activation.

### Replace

- Android’s current “not available yet” personalization surface with real local Vocabulary, Snippets, and Replacements surfaces. (Implemented with bounded SQLite storage and legacy preference migration; DataStore settings migration remains.)
- The current config-only vocabulary list as the canonical personalization store.
- The current Android-only backend assumption with an `SttEngine` adapter boundary.

### Archive

- Historical training outputs and experiment scripts remain outside the active runtime path; their current ignored location is `training/cleanup-llm/output/`.
- Stitch/reference UI assets remain documentation/design evidence, not runtime dependencies.

### Delete only after proof

No deletion is authorized by this audit alone. Rust compiler warnings identify candidates (`copy_fallback`, `clear_if_ours`, unused capture fields, unused insertion helpers, and the nested VAD test), but each needs call-site and replacement-coverage confirmation before removal.

## Immediate sequence

1. Add portable core contracts and schema tests.
2. Implement local personalization repositories and deterministic rule behavior.
3. Wire Android surfaces and IME recovery around those contracts.
4. Add model package validation/benchmark registration.
5. Implement local-first sync contracts and Firebase rules only after local behavior is complete. (Contracts, persisted outbox, rules, and emulator tests are present and locally verified; authenticated provider wiring remains.)
6. Build Linux and Windows shells against the same contracts.

## Known verification blockers

- ADB and Android Gradle are available through the current emulator and writable Gradle cache override. Onboarding, IME selection, and visible rehearsal-keyboard behavior are verified; full live speech/insertion is still not verified.
- GitHub authentication is available for the current CLI account; production review/merge remains a repository-owner decision.
- Firebase emulator rules tests pass locally. No production cloud mutation was attempted.
