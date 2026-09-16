# Test inventory

Date: 2026-09-16

## Current automated coverage

`cargo test --workspace` passed 82 tests on 2026-09-16, with 1 hardware streaming test ignored. The current breakdown is 41 core unit tests, 4 core config integration tests, 6 protocol-abuse tests, 15 portable desktop tests, 3 worker pipe tests, and 14 daemon tests (including package-validation coverage; one of those is the ignored hardware test). The run emitted warnings, but no test failures.

Coverage includes state transitions, protocol limits, reconciliation, VAD/audio-front-end contracts, config validation, filler/repetition cleanup, insertion chord construction, clipboard deadlines, and worker silence behavior.

## Android coverage added in this slice

Added pure reducer and input-policy tests in `android/app/src/test/.../DictationControllerTest.kt` covering stale callbacks, endpointing/finalization, insertion-failure text retention, retry token freshness, password-field blocking, permanent-denial routing, microphone recovery targeting, and editor-action labels. Gradle 8.9 executed all 8 tests successfully on 2026-09-16.

## Android runtime verification

Gradle unit tests executed all 8 Android policy/reducer tests successfully on 2026-09-16. Connected instrumentation executed all 6 Android tests successfully on `emulator-5554` on 2026-09-16, including legacy-preferences migration into SQLite, top-level Home/Personalize/Settings navigation, and the final onboarding recovery path. Manual ADB smoke testing also confirmed the installed APK reaches onboarding, the Vaani IME can be enabled and selected, and the rehearsal field displays the Vaani keyboard even when the emulator advertises a hardware keyboard.

## Missing coverage

- Automated Android coverage for IME lifecycle, permission denial/recovery, rotation, large-font, dark-mode, password-field, and local data flows.
- Windows/Linux cross-platform contract tests for shortcut, insertion, clipboard fallback, and transcript preservation.
- Android SQLite repository instrumentation and schema-migration tests; portable vocabulary/snippet/replacement persistence tests remain partial.
- Cross-device sync-provider integration beyond the Firestore rules boundary.
- Model manifest validation and benchmark regression tests.
- Full Android IME dictation with live speech and insertion on the emulator; the installed APK launch, onboarding flow, IME selection, and visible rehearsal keyboard were smoke-tested through ADB on 2026-09-16.
- Native Linux/Windows desktop adapter behavior and end-to-end focused-editor insertion.
- Live X11 clipboard and focused-editor insertion; the verification host lacks
  the optional `xclip` and `xdotool` tools.

## Test policy for next slices

Every new contract gets platform-neutral tests first. Platform shells then add adapter/lifecycle tests. Text preservation and privacy failures are release blockers.
