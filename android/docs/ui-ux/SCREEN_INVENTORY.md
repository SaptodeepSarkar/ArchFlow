# Screen inventory

Status: Phase 1 discovery  
Date: 2026-09-14

## Existing production surfaces

| ID | Surface | Entry | Current states | Main actions | Data source |
|---|---|---|---|---|---|
| E-01 | Onboarding | First launcher run | Pages 1–3 only | Continue, Back, Finish | Local page integer; `SharedPreferences` completion flag |
| E-02 | Control-plane settings | Launcher after onboarding | Keyboard enabled/not enabled; microphone granted/not granted; selected preferences | Open IME settings, show picker, request microphone, change preferences | Android system APIs + `SharedPreferences` |
| E-03 | Alphabet keyboard | Select Vaani IME in a text field | Lowercase/Shift; guide visible/hidden; suggestion row empty/populated | Type, delete, cursor scrub, symbols, picker, send, hold-to-dictate | `EditorInfo`, `InputConnection`, spell checker, preferences |
| E-04 | Symbols keyboard | Tap `?123` | Symbols | Type symbols, switch ABC, delete, picker, send/dictate | Local keyboard state |
| E-05 | Numeric keyboard | Focus number-class editor | Numeric | Type numbers/decimal, delete, send/dictate | `EditorInfo` |
| E-06 | Dictation-in-keyboard | Hold Send | Listening, finishing, inserted, cancelled, timeout/error as status strings | Release, Cancel | `OnDeviceSttEngine`, cleanup, `InputConnection` |
| E-07 | Android IME settings | Tap Enable Vaani | External system UI | Enable/disable IMEs | Android Settings |
| E-08 | Android IME picker | Tap Choose keyboard / keyboard key | External system UI | Select IME | `InputMethodManager` |
| E-09 | Android microphone permission | Tap Allow microphone | External system UI | Allow/deny | Android runtime permission API |

## Current-state gaps per surface

### E-01 Onboarding

- No live integration or permission status.
- No contextual permission rationale immediately before the system sheet.
- No model/recognizer availability check.
- No invocation choice; only the custom IME exists.
- No test dictation.
- No denial or recovery page.
- No saved page state.
- Fixed illustration height and looping decorative animation.

### E-02 Control plane

- No prioritized readiness status.
- No Home/Personalize/History/Settings shell.
- Does not re-check external system state in `onResume`.
- All preferences are presented in one long view.
- Unsupported model availability is described in prose instead of a state.

### E-03–E-05 Keyboard

- Key targets are visually and physically compact (34 dp rows).
- Rebuilding the whole keyboard is the primary render mechanism.
- Suggestions use system spell-check plus a small hard-coded fallback word list.
- Theme changes are captured when the service's lazy `Ui` is first accessed and may not refresh until service recreation.

### E-06 Dictation

- No explicit state enum/sealed model.
- No partial transcript.
- Finishing and errors occupy the same small status line.
- Insertion failure does not preserve recoverable text.
- Empty recognition is treated as successful delivery internally.
- Error codes are shown as raw numeric recognizer errors in one path.
- The continuous level surface is 88 dp tall, larger than the directive's preferred compact keyboard-adjacent indicator.

## Proposed inventory, gated by actual capability

This is an inventory for design sequencing, not a claim that each surface is implemented.

| ID | Proposed surface | Priority | Capability gate | Phase |
|---|---|---:|---|---:|
| P-01 | Dictation pill/state surface inside Vaani IME | P0 | Existing IME + STT; recovery buffer must be added | 3 |
| P-02 | Insertion recovery panel | P0 | Retained final text + explicit clipboard/retry behavior | 3 |
| P-03 | Welcome | P0 | None | 4 |
| P-04 | Device speech readiness | P0 | Query Android on-device recognizer availability | 4 |
| P-05 | Microphone education and permission result | P0 | Existing runtime permission | 4 |
| P-06 | Keyboard integration education/status | P0 | Existing IME system settings + picker | 4 |
| P-07 | Invocation education | P0 | Custom IME only unless product scope changes | 4 |
| P-08 | Test dictation | P0 | Reusable STT session outside or within a controlled editor | 4 |
| P-09 | Setup complete | P0 | Verified recognizer, permission, IME, and successful test | 4 |
| P-10 | Home — ready | P0 | Coherent readiness model | 5 |
| P-11 | Home — next blocker | P0 | Coherent readiness model | 5 |
| P-12 | Settings root | P0 | Existing preferences | 5 |
| P-13 | Dictation settings | P0 | Cleanup/language controls only at first | 5 |
| P-14 | Appearance & feedback | P1 | System/light/dark and supported feedback settings | 5 |
| P-15 | Privacy & data | P1 | Factual static runtime/storage state + real delete actions | 5 |
| P-16 | Diagnostics | P1 | Real recognizer, service, permission, and version state | 5 |
| P-17 | Personalize landing | P1 | At least one backed personalization capability | 5 |
| P-18 | Vocabulary list/add/edit | P1 | Storage, recognizer-bias integration, validation | 5 |
| P-19 | Snippets list/add/edit | P1 | Storage, unambiguous trigger matcher, insertion integration | 5 |
| P-20 | Replacements list/add/edit/test | P1 | Storage and deterministic transform stage | 5 |
| P-21 | History | P2 | Explicit retention policy + secure local persistence | 6 |
| P-22 | Correction/teach flow | P2 | History + correction/vocabulary semantics | 6 |
| P-23 | Per-app styles | P2 | App context + enforceable formatter settings | 6 |
| P-24 | Model manager | Blocked | Downloadable Android model/runtime and progress API | 5+ |
| P-25 | External floating overlay | Blocked | Product authorization + suitable Android integration | 3+ |

## Proposed navigation at current capability

The directive names four eventual destinations: Home, Personalize, History, Settings. Showing dead tabs would violate truthfulness. Until persistence-backed Personalize and History exist, the truthful V1 shell should be:

```text
Home
Settings
```

When the first personalization engine ships:

```text
Home
Personalize
Settings
```

Only add History after retention and storage ship:

```text
Home
Personalize
History
Settings
```

On a small Views codebase, a compact bottom bar can be introduced without a framework migration. Larger widths should cap the content column before a navigation rail/list-detail investment.

## Preview matrix required before Phase 5 implementation

The directive requests previews before the entire redesign. The following set is adjusted for truthfulness:

| Preview | Design now? | Implementation gate |
|---|---|---|
| Home ready / setup blocked | Yes, after Phase 2 tokens | Real readiness state |
| Onboarding permission / test | Yes | Real permission callback and test session |
| IME listening / finalizing | Yes | Explicit dictation state |
| Insertion failure recovery | Yes | Retained result |
| Dark equivalents | Yes | Dark semantic tokens |
| Vocabulary/snippets/replacements | Wireframe only until semantics approved | Persistence/runtime |
| Model manager | State specification only | Native model/download backend |
| History/app styles | Omit from production previews | Backend unavailable |

