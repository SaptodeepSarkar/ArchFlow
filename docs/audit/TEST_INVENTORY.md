# Test inventory

Date: 2026-09-16

## Current automated coverage

`cargo test --workspace` passed 64 tests on 2026-09-16, with 1 hardware streaming test ignored. The current breakdown is 35 core unit tests, 4 core config integration tests, 6 protocol-abuse tests, 3 portable desktop tests, 3 worker pipe tests, and 14 daemon tests (including the package-validation coverage). The run emitted warnings, but no test failures.

Coverage includes state transitions, protocol limits, reconciliation, VAD, config validation, filler/repetition cleanup, insertion chord construction, clipboard deadlines, and worker silence behavior.

## Android coverage added in this slice

Added pure reducer tests in `android/app/src/test/.../DictationControllerTest.kt` covering stale callbacks, endpointing/finalization, insertion-failure text retention, and retry token freshness. Gradle 8.9 executed all 4 tests successfully on 2026-09-16.

## Missing coverage

- Android instrumentation, IME lifecycle, permission denial/recovery, rotation, large-font, dark-mode, password-field, and local data tests.
- Windows/Linux cross-platform contract tests for shortcut, insertion, clipboard fallback, and transcript preservation.
- Android SQLite repository instrumentation and schema-migration tests; portable vocabulary/snippet/replacement persistence tests remain partial.
- Cross-device sync-provider integration beyond the Firestore rules boundary.
- Model manifest validation and benchmark regression tests.
- Full Android IME dictation with live speech and insertion on the emulator; the installed APK launch and onboarding screen were smoke-tested through ADB on 2026-09-16.
- Native Linux/Windows desktop adapter behavior and end-to-end focused-editor insertion.

## Test policy for next slices

Every new contract gets platform-neutral tests first. Platform shells then add adapter/lifecycle tests. Text preservation and privacy failures are release blockers.
