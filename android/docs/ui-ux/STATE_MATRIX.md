# UI state matrix

Status: Phase 1 discovery  
Date: 2026-09-14

This matrix distinguishes current behavior from the state model required by the directive. Proposed states are design contracts, not implemented claims.

## 1. App readiness

### Required coherent state

```text
AppReadiness
  Checking
  ActionRequired(blocker, nextAction)
  Ready(recognizer, language, invocation)
  Degraded(reason, availableActions)
  Error(reason, repairAction)
```

Blockers must be prioritized in this order for the current IME product:

1. on-device recognizer unavailable;
2. microphone permission missing;
3. Vaani IME not enabled;
4. successful test not completed.

Selection of Vaani as the current IME cannot be reliably treated as a durable app preference; the system picker remains the explicit user action.

| Condition | Current rendering | Required rendering | Primary action |
|---|---|---|---|
| Checking | None; checks are synchronous during render | Quiet in-place status only if a real async check exists | None |
| Recognizer unavailable | Discovered only after holding Send | `Action required — On-device speech unavailable` | Open relevant Android speech settings if a valid intent is identified; otherwise show device-specific guidance |
| Microphone denied | A settings button in the long screen; keyboard status line | `Microphone is off` with contextual explanation | Request permission or open app settings after permanent denial |
| IME disabled | Section prose plus two filled buttons | Single prioritized integration task | Open Android IME settings |
| Ready | Prose says enabled | `Ready · Device speech · Vaani keyboard` | Start a truthful test dictation |
| API 26–30 | Install allowed, dictation fails | Degraded/unsupported recognizer state | Explain requirement or use approved fallback |

## 2. Onboarding

### Required state

```text
OnboardingState(
  step,
  recognizerState,
  microphoneState,
  imeEnabled,
  testState
)
```

| Step | Entry condition | Success condition | Denial/failure | Resume behavior |
|---|---|---|---|---|
| Welcome | First launch | User chooses setup | User exits | Keep onboarding incomplete |
| Speech readiness | Setup started | On-device recognizer reports available | Explain device limitation truthfully | Re-query |
| Microphone education | Recognizer usable | Permission granted | Respect Not now; explain limited behavior | Re-check permission |
| IME integration | Permission granted or skipped | Service is in enabled IME list | Explain that system setting was not changed | Re-check enabled list |
| Invocation | IME enabled | User has seen hold/release interaction | No alternate method exists | Keep custom-IME wording |
| Test dictation | Preconditions met | Non-empty result is safely shown/inserted in controlled test | Preserve result/error and retry | Retain current step/result |
| Complete | Successful test | Completion flag recorded | Never infer from page position | Render Home readiness |

## 3. Dictation

### Current implicit state

Current behavior is distributed across:

```text
voice: Boolean
released: Boolean
recognitionText: String?
generation: Int
engine: OnDeviceSttEngine?
```

### Required explicit state

```text
DictationState
  Hidden
  Starting
  Listening(level)
  Endpointing
  Finalizing
  Inserting(text)
  Success
  Cancelled
  Failure(kind, message, recoverableText?)

FailureKind
  Permission
  Microphone
  RecognizerUnavailable
  Recognition
  Timeout
  Insertion
```

Partial text is intentionally absent until the backend supplies it.

| State | Trigger | UI | Allowed actions | Exit guarantee |
|---|---|---|---|---|
| Hidden | Keyboard shown, no session | Compact ready affordance; keys fully active | Type; hold Send | No audio capture |
| Starting | Hold threshold reached | Immediate `Starting…`; compact level at rest | Cancel | No claim of listening before recognizer readiness |
| Listening | `onReadyForSpeech` | `Listening · Release to finish`; real level | Release; Cancel | Level reflects callback only |
| Endpointing | User releases and `stop()` is sent | `Finishing…` | Cancel after threshold if supported | No more fake amplitude |
| Finalizing | Recognition callback pending after endpoint | Subtle progress label | Cancel on long delay | No percentage |
| Inserting | Clean text available | Brief protected transition | None for sub-second commit | Text retained until commit outcome known |
| Success | Commit accepted | Small acknowledgement, then ready keyboard | Continue typing | Inserted text is primary feedback |
| Cancelled | Explicit Cancel or touch cancel | `Dictation cancelled`, then ready | Retry | Generation invalidated; never insert |
| Failure: permission | Permission absent | Specific repair message | Open app settings | No capture started |
| Failure: microphone | Recognizer start error | Specific retry guidance | Retry | No transcript claimed |
| Failure: recognizer | API/service/model absent | Explain device speech requirement | Open guidance/settings | No fake model-ready state |
| Failure: recognition | Recognizer error/no speech | Human-readable message | Retry | Do not show raw numeric error alone |
| Failure: timeout | Listening/finalizing deadline | Explain stage and retry | Retry | Engine cancelled/released |
| Failure: insertion | `commitText` returns false | `Your dictation is safe` + short preview | Copy; Try again; Dismiss | Recoverable text stays until explicit discard/copy/success |

### Invalid combinations to prevent

- Listening and finalizing simultaneously.
- Success after explicit cancellation.
- Animated audio levels after release/cancel.
- `Text inserted` when the result was empty.
- Insertion failure without `recoverableText`.
- A stale recognizer callback mutating a newer session.

## 4. Permission state

```text
PermissionState
  Granted
  NotRequested
  DeniedCanAskAgain
  DeniedOpenSettings
```

| State | What is known | UI action |
|---|---|---|
| Granted | `checkSelfPermission == GRANTED` | Continue |
| NotRequested | No reliable permanent-denial signal stored yet | Explain use, then request |
| DeniedCanAskAgain | `shouldShowRequestPermissionRationale == true` | Show concise rationale, then request |
| DeniedOpenSettings | A request was made and the platform no longer offers the dialog | Explicit Open settings + Not now |

The app needs a small persisted `microphone_requested` fact to distinguish first request from the no-dialog state on relevant Android versions. Opening Settings must never be treated as a grant.

## 5. On-device recognizer/model state

The current backend can truthfully expose only:

```text
DeviceRecognizerState
  Checking
  Available
  Unavailable(minimumOsOrServiceReason)
  StartFailed(message)
```

It cannot truthfully expose the directive's downloadable-model state machine (`DOWNLOADING`, `VERIFYING`, progress, size, hash, update available). Those states remain blocked until a Vaani-owned Android runtime exists.

## 6. Keyboard state

```text
KeyboardUiState(
  layout: Alphabet | Symbols | Numeric,
  shifted: Boolean,
  guideVisible: Boolean,
  suggestions: List<String>,
  dictation: DictationState
)
```

Rules:

- Numeric layout is derived from the active editor, not a persisted user selection.
- Shift is irrelevant in Symbols/Numeric.
- Suggestion updates must not rebuild active dictation state.
- Voice mode may visually quiet keys but must keep Cancel reachable at an accessible size.
- Theme must be resolved per input-view creation or react to preference changes.

## 7. Preferences

| Preference | Current values | Capability status | Redesign handling |
|---|---|---|---|
| `language` | `en-IN`, `hi-IN`, `bn-IN` | Device-dependent; not validated | Show actual device dependency or constrain to proven language |
| `cleanup` | Boolean | Available | Rename to concrete behavior and show a tiny truthful example |
| `theme` | light/dark/forest/blush | Available but not system-aware | Move toward System/Light/Dark; retain extras only with product approval |
| `accent` | default/lilac/coral/custom int | Available UI styling only | Defer theme editor; one strong brand accent is preferred |
| `background` | paper/grain/image | Available UI styling only | Remove from P0; imagery must have known provenance/license |
| `keyboard_guide` | Boolean | Available | Replace with non-blocking, one-time in-context hint |
| `onboarding_v2` | Boolean | Available but weak semantic | Version next flow and record verified completion separately |

## 8. Personalization, history, and model-management states

These states are intentionally **not yet production UI states**.

| Area | Missing state/backend contract |
|---|---|
| Vocabulary | Entity schema, aliases/category semantics, CRUD, search, recognizer prompt/bias integration, conflict policy |
| Snippets | Entity schema, exact trigger semantics, match order, CRUD/search, conflict handling, expansion stage |
| Replacements | Entity schema, case/word-boundary behavior, transform order, CRUD/search/test, loop/conflict prevention |
| History | Retention choice, encrypted/local storage decision, entity schema, deletion/undo, sensitive preview policy |
| Models | Catalog, installed artifacts, storage requirement, download worker, progress, verification, runtime readiness |
| App styles | Package/app context, supported formatter knobs, fallback/default behavior |

## 9. Phase 1 acceptance check

- [x] Current UI stack identified.
- [x] Current navigation identified.
- [x] State holders and absence of ViewModels identified.
- [x] Dictation interfaces and lifecycle inspected.
- [x] Overlay/invocation reality identified as IME-bound.
- [x] Implemented model capability separated from the native-model seam.
- [x] Manifest permissions inspected.
- [x] Persistence layer inspected.
- [x] Model download/runtime APIs confirmed absent.
- [x] Failure/recovery gaps recorded.
- [ ] Invocation product decision approved.
- [ ] Phase 2 foundation work approved.

