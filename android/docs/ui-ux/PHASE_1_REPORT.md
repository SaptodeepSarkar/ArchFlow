# Phase 1 report — discovery

Date: 2026-09-14  
Decision gate: awaiting product approval before Phase 2

## What changed

- Added an evidence-backed repository/UI audit in [`UI_UX_BASELINE.md`](UI_UX_BASELINE.md).
- Added the current and capability-gated proposed surfaces in [`SCREEN_INVENTORY.md`](SCREEN_INVENTORY.md).
- Added readiness, onboarding, permission, keyboard, and dictation state contracts in [`STATE_MATRIX.md`](STATE_MATRIX.md).
- Made no production Kotlin, resource, manifest, Gradle, or preference changes.
- Discarded the pre-directive generated onboarding image. It had not been referenced by code and its confirmation-sparkle treatment conflicted with the directive's restrained visual-asset rules. No generated asset is being proposed for approval in Phase 1.

## Validation

Run from `android/`:

```text
./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

Result:

```text
BUILD SUCCESSFUL in 8s
46 actionable tasks: 3 executed, 43 up-to-date
```

Test reality:

- `testDebugUnitTest`: `NO-SOURCE` — there are no Android unit tests.
- No instrumentation/UI/screenshot tests were found or run.
- `assembleDebug`: successful.
- `lintDebug`: 0 errors, 28 warnings.

Important lint groups:

- touch listeners do not route clicks through `performClick`, affecting accessibility;
- Canvas drawing allocates `Rect`/`RectF` objects during draw operations;
- hard-coded UI strings are not localizable;
- the 1.7 MB hero bitmap is in a densityless `drawable/` directory;
- custom Views lack layout-editor constructors;
- backup configuration needs the Android 12+ data-extraction form;
- one dependency-update notice.

The generated reports remain under `android/app/build/reports/` and are build output, not source deliverables.

## Manual scenario status

No emulator or physical-device interaction was performed in Phase 1. The directive's scenarios require real Android UI/system permission/IME interaction and remain open:

- first install and permission denial/recovery;
- normal dictation;
- cancel with no insertion;
- insertion failure recovery (currently impossible because text is discarded);
- permission revocation and refresh;
- dark mode and large font;
- offline behavior.

Vocabulary, snippet, replacement, history, model-download, and external-overlay scenarios are blocked by missing backends.

## Known blockers

1. Product decision: custom replacement IME vs separate overlay/coexistence architecture.
2. Transcript recovery contract for failed insertion.
3. Android V1 speech runtime: OEM recognizer vs native Vaani model.
4. Functional support policy for API 26–30.
5. Persistence/runtime semantics for Vocabulary, Snippets, and Replacements.
6. History privacy/retention decision.
7. Provenance/license record for the existing `vaani_hero.png` before reusing it in a new visual system.

## What remains after approval

Phase 2, per the directive:

- information architecture and user flows;
- design tokens, typography, shapes, spacing, elevation, and motion;
- system bars/insets and adaptive max-width behavior;
- shared semantic components;
- navigation shell appropriate to available features;
- preview strategy and baseline screenshot harness;
- immutable state-holder pattern compatible with the existing Views stack.

Production dictation behavior is Phase 3 and onboarding is Phase 4. They should not be mixed into a single unreviewable rewrite.

## Approval request

Approve one invocation direction before Phase 2 begins:

```text
A. IME-first V1
   Keep Vaani as the selected keyboard and redesign its dictation surface.

B. Coexisting overlay
   Authorize a new Android integration so Vaani can sit above another keyboard.
   This is a larger permissions, lifecycle, privacy, and backend scope.
```

The evidence currently favors **A: IME-first V1** because it preserves the only working insertion path and avoids inventing a sensitive integration.

