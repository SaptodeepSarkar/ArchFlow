# Vaani Android UI/UX baseline

Status: Phase 1 discovery  
Date: 2026-09-14  
Source of truth: [`docs/Vaani-Android-UI-UX-Agent-Directive-v2.md`](../../../docs/Vaani-Android-UI-UX-Agent-Directive-v2.md)

This document records what the Android application actually does before the redesign. It deliberately separates working capability from seams and product ideas. No Phase 2 UI is implied to work merely because it appears in the directive.

## Executive finding

The current Android product is a small, programmatic Views application with two surfaces:

1. a launcher Activity used for onboarding and preferences;
2. a custom `InputMethodService` that is both the keyboard and the dictation surface.

The daily-use path is real and local-first in structure: select the Vaani IME, hold its Send key, speak, release, and commit the result into the focused editor. It does **not** currently provide the directive's separate floating pill over a preferred third-party keyboard. It replaces the user's keyboard while selected.

The strongest redesign path is incremental. Preserve the working IME, speech-recognizer boundary, cleanup boundary, and direct `InputConnection` insertion. First fix the dictation state model and recoverability inside the IME; then rebuild setup and the control plane around capabilities that actually exist.

## Repository inventory

| Area | Current implementation | Assessment |
|---|---|---|
| UI framework | Kotlin, classic Android Views, all layouts created in code | Keep for the first redesign. A Compose migration is not justified by current size or dependencies. |
| App shell | One `Activity`, no fragments, router, ViewModel, or saved-state model | Navigation and coherent screen state do not yet exist. |
| Onboarding | Three-page `LinearLayout` inside a `ScrollView` | Informational carousel; it does not verify completion or survive process recreation explicitly. |
| Control plane | One long settings `ScrollView` | No Home/Personalize/History/Settings information architecture. |
| Daily-use surface | Custom `InputMethodService` keyboard | Working invocation and insertion path; not a system-wide floating overlay. |
| Speech | Android `SpeechRecognizer.createOnDeviceSpeechRecognizer` on API 31+ | Real on-device API use, but availability is OEM/model-dependent and absent on API 26–30 despite `minSdk 26`. |
| Model runtime | Android-provided on-device speech service | No bundled Vaani model, download, verification, warm state, progress, or runtime metrics. |
| Cleanup | Local whitespace collapse, first-letter capitalization, and terminal punctuation | Real and deterministic. No learned formatter or list transformation. |
| Persistence | `SharedPreferences` only | Stores onboarding, guide, language, cleanup, theme, accent, and background choices. No structured user content. |
| Tests | No Android unit, instrumentation, screenshot, or UI tests in the module | The current build can compile, but behavior is unguarded. |

## Current navigation

There is no navigation stack.

```text
Launcher
  ├─ onboarding_v2 = false → OnboardingView (3 local pages)
  └─ onboarding_v2 = true  → one scrolling preferences screen

Android keyboard settings / picker
  └─ VaaniKeyboardService → custom keyboard + hold-to-dictate
```

The Activity opens Android input-method settings, the input-method picker, and the runtime microphone permission sheet. Returning to the Activity does not trigger an explicit state refresh in `onResume`; `render()` is only called from initial creation and local UI callbacks.

## Existing UI surfaces

### Launcher Activity

- Forces immersive mode by hiding status and navigation bars.
- Shows onboarding until `onboarding_v2` is set.
- After onboarding, shows keyboard readiness, input-method actions, microphone permission, language, cleanup, theme, accent, background, and a usage explanation.
- Rebuilds the entire view tree for each preference change and manually restores scroll offset.
- Uses one visual treatment for most actions, including selection choices.

### Onboarding

- Page 1 explains enabling the keyboard, choosing it, and allowing microphone access.
- Page 2 teaches hold-to-speak.
- Page 3 teaches release-to-insert and cancel.
- Uses one continuously looping custom Canvas animation for all pages.
- Completion records only that the last page was reached. It does not confirm keyboard enabled, microphone granted, keyboard selected, or a successful dictation.

### Keyboard and dictation

- Provides alphabet, symbol, and numeric layouts.
- Supports Shift, repeat-delete, space-bar cursor scrubbing, input-method picker, editor action/return, and up to three spelling suggestions.
- A press held for 220 ms starts dictation; release stops and later inserts.
- Shows real RMS-derived bars while listening.
- Cancel invalidates the session generation and does not insert.
- Password variations block voice input.
- A 120-second listening timeout and 15-second finish timeout exist.
- The normal Send action can submit an editor action; voice completion only inserts text and does not send.

## Feature-capability matrix

Definitions:

- **AVAILABLE**: a usable implementation exists now.
- **PARTIALLY_AVAILABLE**: a real implementation exists with a material limitation.
- **PLANNED**: an explicit code boundary or repository handoff exists, but not a product capability.
- **UNAVAILABLE**: no implementation was found.

| Capability | Status | Evidence / constraint | Production UI decision |
|---|---|---|---|
| Custom Android IME | AVAILABLE | Declared `InputMethodService`; direct `InputConnection` typing and insertion | Preserve and make it the truthful invocation method. |
| Enable keyboard | AVAILABLE | Opens `Settings.ACTION_INPUT_METHOD_SETTINGS` | Onboarding may guide this and must re-check on return. |
| Choose keyboard | AVAILABLE | Opens Android input-method picker | Expose as an explicit system step. |
| Microphone permission | AVAILABLE | Runtime `RECORD_AUDIO` request | Prime in context, then show the real system prompt. |
| On-device Android STT | PARTIALLY_AVAILABLE | Requires API 31+ and an OEM-installed on-device recognizer/model | Report actual availability. Do not equate it with a bundled Vaani model. |
| English dictation | PARTIALLY_AVAILABLE | Defaults to `en-IN`; actual language model depends on device | Offer only as device-provided language selection, not a downloaded Vaani model. |
| Hindi/Bengali selection | PARTIALLY_AVAILABLE | Locale tags are sent, but availability/readiness is not queried | Do not claim installed or supported; label as device-dependent if retained. |
| Real audio-level feedback | AVAILABLE | `onRmsChanged` drives a 40-sample Canvas level view | Preserve, throttle/render cheaply, stop immediately with capture. |
| Partial transcript | UNAVAILABLE | `EXTRA_PARTIAL_RESULTS=false`; callback is ignored | Do not show fake partial text. |
| Stable prefix | UNAVAILABLE | No backend signal | Do not design as functioning state. |
| Hold/release invocation | AVAILABLE | Send-key touch listener with 220 ms threshold | Make the gesture and release behavior unmistakable. |
| Tap Send / editor action | AVAILABLE | Short press invokes editor action or newline | Preserve; voice must not auto-send. |
| Cancellation | AVAILABLE | Cancel button and generation invalidation | Preserve; increase target size and model as explicit state. |
| Password-field protection | AVAILABLE | Known text/number password variations are checked | Preserve; test more editor variations later. |
| Deterministic light cleanup | AVAILABLE | Whitespace, capitalization, final punctuation | UI may expose this exact behavior with a truthful example. |
| Learned/LLM cleanup | PLANNED | `CleanupEngine` seam and README handoff only | Omit from production UI until an Android engine exists. |
| Bundled PCM STT | PLANNED | `PcmSttEngine` interface only | No model card/download state may claim readiness. |
| V5 model on Android | UNAVAILABLE | Desktop CTranslate2 artifact explicitly not bundled or benchmarked | Document as backend blocker. |
| Text insertion | AVAILABLE | `InputConnection.commitText` | Preserve selection behavior supplied by Android; add spacing tests. |
| Insertion failure recovery | UNAVAILABLE | Failure reduces to a status string; result is discarded by `cancelVoice()` | P0 blocker: retain text and offer copy/retry before visual redesign. |
| External floating overlay | UNAVAILABLE | No overlay permission/service/window implementation | Do not show it as a working invocation option. |
| Coexistence with another IME | UNAVAILABLE | Vaani itself is the selected IME | Directive's preferred above-keyboard pill cannot be claimed without a new integration design. |
| Quick Settings tile | UNAVAILABLE | No `TileService` | Omit. |
| Accessibility integration | UNAVAILABLE | No `AccessibilityService` | Omit; do not request sensitive access. |
| Foreground notification | UNAVAILABLE | No foreground service/channel | Omit. |
| Vocabulary | UNAVAILABLE | No storage, matching API, or UI | P1 backend/product work required before production UI. |
| Snippets | UNAVAILABLE | No storage, expansion semantics, or UI | P1 backend/product work required. |
| Replacements | UNAVAILABLE | No storage or deterministic replacement engine | P1 backend/product work required. |
| History | UNAVAILABLE | No transcript persistence; current flow avoids it | Do not include a History destination in V1 navigation until policy and storage exist. |
| Per-app styles | UNAVAILABLE | No app-context or formatter control | Omit. |
| Diagnostics export | UNAVAILABLE | No diagnostics model/export | A read-only capability screen can come later only from real state. |
| Dynamic color | UNAVAILABLE | Hard-coded palettes; no Material 3 dependency | Phase 2 may create a restrained fallback theme; dynamic color requires a deliberate dependency/API decision. |
| Dark theme | PARTIALLY_AVAILABLE | User-selectable hard-coded dark palette | Needs contrast/system-bar/keyboard QA; not system-aware. |
| Reduced motion | UNAVAILABLE | Onboarding animator loops whenever attached | Phase 2 must honor disabled animator scale and avoid decorative loops. |
| Large-screen adaptation | UNAVAILABLE | Full-width linear layouts and fixed heights | Phase 2 must add max-width/adaptive treatment. |

## Reusable implementation boundaries

- `SttEngine`: viable injection seam for recognizers with `start`/`stop` lifecycle.
- `PcmSttEngine`: viable future native-engine contract, currently unused.
- `CleanupEngine`: clean separation between recognition and formatting.
- `ConservativeCleanup`: safe, deterministic implementation worth retaining and testing.
- Generation token in the IME: useful stale-session guard.
- `InputConnection`: correct platform boundary for IME insertion.
- `Palette`/`Ui`: an embryonic token/component layer, but it mixes design tokens, preference lookup, background rendering, and widget factories.
- `Wave`: a cheap real-amplitude visualization, although its state ownership should move under a dictation UI state.

## Obsolete or redesign candidates

- The marketing-style three-page onboarding carousel.
- Completion based on reaching page 3 rather than successful setup.
- Immersive system-bar hiding in the control-plane Activity.
- The single long settings screen and button-as-radio pattern.
- The photo used as a full-screen application texture; its source/license is not recorded in the Android tree.
- Theme/accent/background editor breadth before core readiness and recovery.
- Decorative looping onboarding motion.
- User-visible spelling inconsistency: UI says **Vanni**, while the product and package documentation say **Vaani**.

## Privacy and trust findings

- The manifest requests only microphone permission plus the binding permission required by Android for the IME service.
- The Android client has no network dependency or declared internet permission.
- Transcripts are passed as Kotlin strings to cleanup and `InputConnection`; no transcript logging, intents, argv, or shell transport was found.
- History and audio retention are absent.
- `createOnDeviceSpeechRecognizer` is the strongest available Android API signal for local recognition, but readiness still depends on the device's installed recognition service/model.
- The app must avoid the broader claim that a Vaani-owned model is installed or that a known model size/runtime exists on Android.

## Accessibility and native-UX findings

- Several keyboard rows are only 34 dp high, the Cancel control is 42 dp, and onboarding header controls have fixed heights. These are below the directive's intended accessible target size.
- Icon-only Shift and Send controls have content descriptions; text/emoji controls rely on visible labels.
- Dynamic listening/status changes do not define live-region behavior, and there is no TalkBack announcement policy.
- Onboarding text and visuals use fixed-height containers that are likely to clip with large font scaling or landscape.
- The Activity hides system bars rather than integrating with insets.
- The app uses serif display text mixed with default sans text without a centralized typography scale.
- Normal enabled/selected/action states are often represented by the same filled button style.
- Some states rely heavily on color and alpha, especially the dimmed keyboard during voice capture.
- Android lint confirms accessibility click-handling warnings for every custom touch listener, draw-time allocations in animated/custom views, hard-coded non-localizable strings, and density handling concerns for the hero bitmap.

## P0 product risks before visual polish

1. **Successful transcript loss on insertion failure.** The recognized string is cleared when insertion fails.
2. **No explicit dictation state model.** Booleans (`voice`, `released`) and nullable text allow UI and lifecycle behavior to drift.
3. **Setup completion is not real completion.** Permission/integration/test success are not verified.
4. **Platform coverage mismatch.** `minSdk 26` installs on devices where this STT implementation categorically cannot run.
5. **No state refresh after Settings round trips.** Opening a settings screen is treated too much like accomplishing the step.
6. **The custom keyboard strategy conflicts with the preferred coexistence strategy.** Product must explicitly accept the Vaani-as-IME approach or authorize a new overlay/accessibility integration.
7. **No UI test seams.** Critical cancel, timeout, insertion, and permission paths have no Android tests.

## Backend/product decisions needed before Phase 2/3

1. Is Vaani's Android V1 invocation strategy intentionally a replacement IME, or should a separate overlay/accessibility path be built?
2. Should API 26–30 remain supported with an alternate recognizer, or should the minimum functional OS be raised to API 31?
3. Is device-provided on-device STT acceptable for V1, or is the native PCM/model runtime a launch blocker?
4. May insertion failures place the recovered transcript on Android's clipboard only after an explicit user action?
5. Are Hindi and Bengali truthful supported choices for V1 on target devices, or should onboarding default to a single device-supported language?
6. Should History remain absent for privacy, or is a retention policy and local database in scope?
7. Are Vocabulary, Snippets, and Replacements UI-only future concepts, or should their storage/runtime semantics be built in P1?

## Recommended phase gate

Approve Phase 2 only after choosing the invocation strategy. The design foundation and navigation hierarchy depend on whether Vaani remains a custom keyboard or gains a separate system overlay. Regardless of that choice, Phase 2 can safely centralize tokens, typography, shapes, spacing, system bars, accessibility sizing, and immutable UI state patterns.
