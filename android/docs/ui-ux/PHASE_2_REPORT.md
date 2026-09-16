# Phase 2–4 implementation report

Date: 2026-09-16

The approved IME-first development path is now implemented as the current V1 surface. The future coexisting invocation remains a clean architectural direction, not a fake option in the app.

## Implemented

- Added shared semantic palette, typography, shape, spacing, button, card, and pill helpers in `Ui.kt`.
- Remixed the brand language around warm cream, forest ink, amber action, sage support, and coral error roles.
- Raised app functional target to Android API 31, matching `SpeechRecognizer.createOnDeviceSpeechRecognizer` availability.
- Replaced immersive system-bar hiding with edge-to-edge-compatible insets handling.
- Added a truthful Home/Settings shell. Home shows one prioritized readiness blocker; Settings contains only implemented language, deterministic cleanup, theme, keyboard, and about controls.
- Rebuilt onboarding into four functional steps: welcome, microphone context, keyboard integration, and a real test-field gate.
- Added persisted onboarding step, microphone-request/granted state, and first-successful-dictation state.
- Added explicit `DictationState` and `FailureKind` models.
- Added `Starting`, `Listening`, `Endpointing`, `Finalizing`, `Inserting`, `Success`, `Cancelled`, and recoverable failure rendering to the IME.
- Preserved recognized text after insertion failure with Copy, Try insertion again, and Dismiss actions.
- Kept real RMS level feedback; decorative onboarding motion stops when Android animators are disabled.
- Corrected user-facing `Vanni` naming to `Vaani`.
- Added Android 12+ data-extraction exclusions because local preferences are private configuration, not portable account data.

## Assets

Generated with the built-in image-generation skill, using `website/assets/vaani-hero.png` only as a mood reference:

- `brand/assets/vaani-android-banner.png` — original warm editorial banner.
- `brand/assets/vaani-flow-ribbon.png` — original transparent paper-ribbon motif.
- `app/src/main/res/drawable-nodpi/vaani_onboarding_banner.webp` — optimized app derivative.
- `app/src/main/res/drawable-nodpi/vaani_flow_ribbon.webp` — optimized app derivative.

The prompts explicitly excluded text, logos, fake UI, neon, particles, sparkles, microphones, and generic AI motifs.

## Validation

```text
GRADLE_USER_HOME=/tmp/vaani-gradle ./gradlew :app:assembleDebug :app:lintDebug
```

Result: `BUILD SUCCESSFUL` for lint, unit tests, and the debug APK; connected instrumentation also completed all 4 tests on `emulator-5554`, including legacy-preferences migration into SQLite. Manual ADB verification confirmed onboarding, microphone permission handling, Vaani IME enablement/selection, and the page-four rehearsal field with the Vaani keyboard visibly rendered. The IME explicitly keeps its input view visible on hardware-keyboard emulators. TalkBack, large-font, landscape, dark-mode, and full live speech/insertion flows still need dedicated QA.

## Deliberately not implemented

- Room/persistence for Vocabulary, Snippets, and Replacements.
- History, app styles, downloadable Vaani models, external overlay, Quick Settings, and AccessibilityService integration.
- Android dynamic color dependency migration.
- A fake partial transcript; the current Android recognizer still requests final-only results.

These remain backend/product gates, not visual placeholders.
