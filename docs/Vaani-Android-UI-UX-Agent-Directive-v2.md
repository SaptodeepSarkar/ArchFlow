# Vaani Android — UI/UX Product & Implementation Directive

> Agent handoff document for designing and implementing the Android UI/UX.
>
> Product: **Vaani**
>
> Product category: Local-first, system-wide intelligent voice dictation.
>
> Core experience: The user speaks naturally in any app; Vaani transcribes, cleans, formats, personalizes, and inserts polished text with minimal visible friction.
>
> This document defines the intended product behavior, information architecture, interaction states, visual system, accessibility rules, implementation priorities, and acceptance criteria. Treat it as the design source of truth unless the existing repository proves that a backend capability is unavailable.

---

# 0. Mission

Design Vaani as an **Android-native dictation utility**, not as:

- a voice recorder;
- a chatbot;
- an AI assistant chat screen;
- a transcription notebook;
- a dashboard full of metrics;
- a clone of another application's visual identity;
- a desktop interface compressed into a phone.

The product should feel like a native Android capability that happens to be installed as an app.

The full-screen app exists primarily to:

1. set Vaani up;
2. manage dictation behavior;
3. manage personal vocabulary;
4. manage snippets;
5. manage deterministic replacements;
6. configure language/model behavior;
7. inspect or correct recent dictation if history is enabled;
8. control privacy and local data;
9. configure per-app writing styles;
10. diagnose model/runtime problems.

The **daily-use experience happens over other applications**, not inside Vaani.

The user should be able to dictate into a text field in WhatsApp, Discord, Gmail, a browser, a code editor, notes, search boxes, or another supported app without navigating through the Vaani application first.

---

# 1. Product personality

Vaani should feel:

- immediate;
- calm;
- precise;
- lightweight;
- private;
- technical when necessary;
- invisible when unnecessary;
- confident without looking futuristic for the sake of it.

Avoid generic "AI product" styling.

Do not fill the UI with:

- glowing purple gradients;
- magic sparkles everywhere;
- robot icons;
- neural-network illustrations;
- excessive glassmorphism;
- animated blobs;
- giant waveform hero cards;
- marketing copy inside functional screens;
- "Ask AI" metaphors;
- chatbot bubbles for dictation.

Vaani is a **tool**.

Its visual quality should come from typography, hierarchy, spacing, motion, shape, state clarity, and excellent micro-interactions.

---

# 2. Primary UX principle: disappear after setup

The user's ideal workflow is:

```text
Open another app
    ↓
focus text field
    ↓
invoke Vaani
    ↓
speak naturally
    ↓
see subtle live feedback
    ↓
stop speaking
    ↓
polished text appears
```

The user should not have to:

```text
open Vaani
→ tap record
→ speak
→ inspect transcript
→ tap copy
→ switch apps
→ paste
```

That is a failed product experience.

The Vaani app is the **control plane**.

The dictation overlay / invocation surface is the **working experience**.

Design both, but optimize the second for frequency and speed.

---

# 3. Non-negotiable UX goals

## 3.1 Invocation

From user intent to active listening should feel immediate.

UI target:

```text
gesture / shortcut / button
        ↓
visual acknowledgement < ~100 ms if possible
        ↓
listening state immediately visible
```

The UI must not wait for the STT model to produce text before showing that dictation has started.

## 3.2 Post-speech

When speech ends:

```text
LISTENING
   ↓
FINALIZING
   ↓
TEXT INSERTED
```

Do not display a blocking progress screen.

Do not show percentage progress for sub-second inference.

Use an understated state transition.

## 3.3 Error recovery

Every failure must answer:

1. What failed?
2. Was the user's text lost?
3. What can they do now?

Never show:

```text
Something went wrong.
```

by itself.

Prefer specific messages such as:

```text
Microphone unavailable
Another app is using the microphone.
```

or:

```text
Model isn't ready
Finish downloading English before using offline dictation.
```

## 3.4 Preservation

The UI must reinforce the product promise that Vaani formats speech without casually changing the user's meaning.

When showing before/after text, emphasize meaningful edits rather than decorating every punctuation change.

---

# 4. Agent rules before writing UI code

Before implementing the redesign:

1. inspect the repository;
2. identify whether UI is Jetpack Compose, XML Views, Flutter, React Native, or another stack;
3. identify current navigation;
4. identify existing ViewModels/state holders;
5. identify dictation-service interfaces;
6. identify current overlay/invocation implementation;
7. identify actual implemented model features;
8. identify current permissions;
9. identify persistence/database layer;
10. identify model-download/runtime state APIs.

Do **not** migrate the entire UI framework just because this specification mentions Compose terminology.

If the project already uses Jetpack Compose, stay in Compose unless there is a compelling technical reason not to.

Do not rewrite working backend logic merely to make UI implementation easier.

Create a short inventory document before large changes:

```text
UI_UX_BASELINE.md
```

Record:

- current screens;
- navigation;
- working features;
- missing backend features;
- reusable components;
- obsolete UI;
- permissions;
- overlay behavior;
- known constraints.

---

# 5. Truthfulness rule

Do not design a fake feature and present it as working.

For every proposed control, determine whether the underlying capability is:

```text
AVAILABLE
PARTIALLY_AVAILABLE
PLANNED
UNAVAILABLE
```

If a feature is not implemented:

- do not silently wire a dead button;
- do not fake success;
- do not claim it works;
- either omit it from production UI or clearly mark it as unavailable during development.

This especially applies to:

- multilingual models;
- app-aware context;
- live editor symbol extraction;
- NPU acceleration;
- cloud sync;
- cross-device sync;
- history;
- learned corrections;
- per-app style;
- custom trigger gestures;
- wake-word behavior.

---

# 6. Android design baseline

Use modern Android conventions.

If using Compose:

- use Material 3 as the baseline component system;
- use stable APIs for production unless the repository deliberately tracks previews;
- support edge-to-edge layout;
- handle status/navigation bar insets correctly;
- support predictive back where appropriate;
- support dynamic window sizing rather than hard-coding one phone dimension;
- ensure tablet/foldable layouts do not simply stretch phone cards across the entire display.

Material 3 Expressive ideas may inform motion, shape, emphasis, and component hierarchy, but do **not** turn every control into an oversized expressive component.

Vaani should remain compact and utility-oriented.

---

# 7. Information architecture

Use four primary destinations:

```text
Home
Personalize
History
Settings
```

On compact phones, use a bottom navigation bar if the current architecture supports it cleanly.

On larger/adaptive layouts, navigation may become a rail or another appropriate navigation treatment.

Do not use five or six top-level destinations unless user testing or existing architecture clearly requires it.

---

# 8. HOME

Home answers one question immediately:

> Is Vaani ready to dictate?

The first viewport should prioritize system status, not marketing.

Recommended hierarchy:

```text
Top app bar
Vaani

Ready state / setup issue

Primary activation/demo control

Quick status
- English model
- On-device
- invocation method

Recent useful actions
```

Do not show a giant dashboard.

---

# 9. Home — ready state

Example conceptual layout:

```text
Vaani

Ready
English • On-device

[ Start test dictation ]

Try saying:
"first buy milk second call Rahul"

────────────────────────

Personal vocabulary     24
Snippets                 6
History                 >

────────────────────────

Runs locally
Audio processing status / privacy entry
```

The exact values must come from real state.

The "Start test dictation" button is for discovering/testing Vaani **inside the app**. It is not intended to become the normal daily workflow.

---

# 10. Home — setup incomplete

If critical setup is missing, replace general content with a single prioritized action.

Example:

```text
Vaani

1 step left

Enable Vaani access
Vaani needs the configured system integration
to place dictated text into other apps.

[ Continue setup ]
```

Never show three equally prominent red warning cards.

Prioritize the next blocking task.

After completion, move to the next blocker.

---

# 11. Home — model not installed

Example:

```text
English model

Fast English
~XX MB

Designed for offline dictation.

[ Download ]

Storage required: XX MB
```

During download:

```text
Downloading English

184 MB of 312 MB
[██████████------] 59%

You can leave this screen.
```

Only show determinate percentage when the backend actually exposes meaningful progress.

States:

```text
NOT_INSTALLED
QUEUED
DOWNLOADING
VERIFYING
READY
UPDATE_AVAILABLE
PAUSED
FAILED
CORRUPTED
INSUFFICIENT_STORAGE
```

Design all states explicitly.

---

# 12. PERSONALIZE

This is the core customization area.

Personalize contains:

```text
Vocabulary
Snippets
Replacements
App styles
```

Do not make all of these separate bottom-navigation destinations.

Use an internal segmented control/tab/list hierarchy appropriate to the available width.

---

# 13. Vocabulary

Purpose:

Teach Vaani words that are unusual, personal, technical, or commonly misrecognized.

Examples:

```text
Saptodeep
Hyprland
Vaani
CUDA
Medhāra
Qwen
```

Vocabulary is not the same thing as deterministic replacement.

Make that distinction understandable.

Screen structure:

```text
Personal vocabulary                     [+]

Words Vaani should recognize correctly.

[ Search vocabulary ]

Hyprland
Technical term
Spoken as: "hyper land"

Saptodeep
Name

Medhāra
Project

CUDA
Technical term
```

Do not display implementation details such as trie weights or decoder scores in the ordinary UI.

Advanced diagnostic information may exist behind an Advanced section.

---

# 14. Add vocabulary flow

Use a bottom sheet or dedicated page depending on complexity.

Fields:

```text
Word or phrase *
[ Hyprland ]

Spoken like
[ hyper land ]

Category
[ Technical term ]

Case sensitive
[ optional / only if backend supports it ]
```

Primary action:

```text
[ Add to vocabulary ]
```

If automatic pronunciation variants exist, do not force users to understand phonemes.

Advanced users may optionally access pronunciation aliases.

Explain "Spoken like" simply:

> Add another way you might say this word.

---

# 15. Vocabulary feedback loop

When Vaani repeatedly sees the user correct the same term, UX may propose:

```text
Teach Vaani "Shreya"?

You corrected "Sharia" to "Shreya" twice.

[ Add ]    [ Not now ]
```

Do not silently learn unlimited corrections unless the underlying product has intentionally chosen that behavior and provides undo/history.

Never interrupt the user's active dictation with this suggestion.

Surface it afterward as:

- a subtle notification;
- history suggestion;
- personalization suggestion.

---

# 16. Snippets

Snippets expand a spoken trigger into exact saved content.

Example:

```text
Trigger
my GitHub

Expands to
https://github.com/example/repository
```

The distinction from vocabulary must be obvious:

```text
Vocabulary:
helps recognize a word.

Snippet:
inserts saved content when you say a trigger.

Replacement:
always changes one recognized phrase into another exact value.
```

Use plain-language explanations.

---

# 17. Snippet list

Conceptual layout:

```text
Snippets                               [+]

[ Search snippets ]

my GitHub
https://github.com/...
Used 18 times

my email
name@example.com
Used 7 times

meeting intro
Hi everyone, thanks for joining...
```

Do not expose the full content of long snippets in the list.

Use one or two preview lines.

---

# 18. Add/edit snippet

Fields:

```text
Spoken trigger *
[ my GitHub ]

Insert *
[ https://github.com/... ]

Match behavior
[ Exact phrase / supported behavior ]

[ Save snippet ]
```

For destructive overwrite of an existing trigger, show a precise conflict:

```text
"my GitHub" already exists.

[ Edit existing ]
[ Use another trigger ]
```

Never allow ambiguous duplicate triggers silently.

---

# 19. Replacements

Replacements are deterministic canonicalizations.

Example:

```text
hyper land  →  Hyprland
my repo     →  github.com/...
```

However, if something inserts a long saved block or URL, prefer classifying it as a snippet rather than blurring the concepts.

Recommended UI:

```text
Replacements                            [+]

[ Search ]

hyper land
→ Hyprland

Q and
→ Qwen

sapto deep
→ Saptodeep
```

Include a test field:

```text
Test a replacement
[ type or paste text ]

Result
...
```

This is valuable because replacements can otherwise become invisible behavior.

---

# 20. Per-app styles

This is a later/optional feature unless the backend already supports it.

Concept:

```text
App styles

WhatsApp
Casual

Gmail
Professional

Discord
Very casual

Default
Balanced
```

Never promise semantic rewriting.

Style should primarily govern supported formatting behavior such as:

- casing;
- terminal punctuation;
- paragraph density;
- emoji behavior;
- list formatting;
- perhaps contraction handling if explicitly supported.

Opening an app entry:

```text
WhatsApp

Writing style
○ Default
● Casual
○ Professional
○ Very casual
○ Custom

Emojis
Automatic / Minimal / Never

Lists
Automatic [on]

[ Reset to default ]
```

If custom style cannot actually be enforced by the formatter, do not expose the option.

---

# 21. HISTORY

History is optional and privacy-sensitive.

Before implementing it, determine whether Vaani actually persists dictations.

If history is intentionally disabled for privacy, do not create a fake History tab.

If enabled, make retention obvious.

History should be useful for:

- recovering recent text;
- copying it again;
- seeing formatting changes;
- correcting recognition;
- teaching vocabulary;
- diagnosing failure.

It should not resemble a social feed or chat conversation.

---

# 22. History item

Example:

```text
8:42 PM • WhatsApp

Can you send the report tomorrow morning?

Before formatting
can you send the report tomorrow morning

[ Copy ] [ Correct ]
```

The "before formatting" disclosure should be collapsed by default.

Do not display audio unless audio is deliberately retained.

If audio is not stored, state that accurately where relevant.

---

# 23. Correct transcription flow

Correction UI has two different intentions:

```text
A. Correct this one transcript.
B. Teach Vaani for the future.
```

Do not confuse them.

Example:

```text
Original
Open the hyper land config.

Corrected
Open the Hyprland config.

[ Save correction ]

☐ Also teach Vaani "Hyprland"
```

If automatic vocabulary suggestions are used, show the consequences clearly.

---

# 24. Delete history

Provide:

```text
Delete this dictation
Clear history
Retention period
```

Use confirmation for clearing everything.

Avoid confirmation dialogs for deleting a single low-value row if undo is available.

Prefer:

```text
History item deleted
[ Undo ]
```

for ordinary single-row deletion.

---

# 25. SETTINGS architecture

Settings should be a conventional Android settings hierarchy.

Suggested groups:

```text
Dictation

Language & models

Personalization

Appearance & feedback

Privacy & data

Performance

Advanced

About
```

Do not put every setting on the root level.

---

# 26. Dictation settings

Possible entries, only when supported:

```text
Invocation method
Automatic punctuation
Remove fillers
Handle self-corrections
Automatic lists
Emoji interpretation
Stop-listening behavior
Insert immediately
```

Every toggle must correspond to deterministic or model behavior that can actually be switched.

Avoid ambiguous toggles like:

```text
AI enhancement
Smart mode
Better text
```

Users should know what a setting changes.

---

# 27. Language & models

Structure:

```text
Language & models

Dictation language
English

English model
Fast English
312 MB
Ready

Model updates
Automatic on Wi-Fi

[ Manage models ]
```

Future multilingual support should fit this structure without redesign.

Do not show unsupported Hindi/Hinglish models as if installed.

If Vaani later supports multiple languages:

```text
English
Hindi
Hinglish / multilingual
```

may appear based on actual model capabilities.

---

# 28. Model detail screen

Model detail can expose:

```text
Fast English

Status
Ready

Size
312 MB

Runtime
CPU

Quantization
INT8

Last updated
...

[ Check for update ]
[ Delete model ]
```

Only surface low-level values such as quantization if useful to the intended user.

A simplified mode can hide them.

Advanced diagnostics may show:

```text
RTF
last inference latency
backend
threads
model hash/version
```

Do not put these engineering metrics on Home.

---

# 29. Performance settings

Vaani is local and performance-sensitive.

Potential settings:

```text
Performance mode
○ Battery saver
● Balanced
○ Fastest

Keep model warm
[ on/off if supported ]

Hardware acceleration
Automatic

CPU threads
Automatic
```

Default users should see understandable presets.

Do not make them choose thread counts, execution providers, or quantization formats during onboarding.

Put manual runtime controls behind Advanced.

---

# 30. Privacy & data

This screen must be factual.

Possible entries:

```text
Processing
On-device / actual runtime behavior

Dictation history
Off / 7 days / 30 days / Forever

Audio retention
actual behavior

Personal vocabulary
Stored locally / actual behavior

Export personalization
Delete local data
```

Never display:

> Your voice never leaves your device.

unless repository/network behavior proves that statement is true in every relevant mode.

If optional online processing exists, state precisely when it is used.

---

# 31. Delete local data

Use clear categories:

```text
Delete local data

History
Vocabulary
Snippets
Replacements
Downloaded models
Preferences

[ Select data ]
```

Do not bundle downloaded model deletion with personal-data deletion without explanation; redownloading a 300 MB model has different consequences from clearing history.

---

# 32. Appearance & feedback

Keep this small.

Possible settings:

```text
Theme
System / Light / Dark

Dynamic color
On / Off

Haptic feedback
On / Off

Listening sound
On / Off

Completion sound
On / Off

Show live transcript
On / Off
```

Respect system reduce-motion / accessibility preferences where available.

Do not build a full theme editor.

---

# 33. Advanced

Advanced can contain developer/diagnostic controls:

```text
Inference backend
CPU / Automatic / supported accelerator

Thread count
Endpoint timeout
Model logs
Export diagnostics
Reset model cache
Context bias debugging
```

Only include controls that actually work.

Put a warning before settings capable of breaking performance.

Example:

```text
Advanced settings

These settings can reduce accuracy or increase battery use.
```

Do not use intimidating security language when it is merely a performance setting.

---

# 34. DICTATION OVERLAY — highest-priority interaction

The overlay is the most important UI in Vaani.

It must:

- be compact;
- never cover large portions of the target app;
- clearly communicate microphone state;
- react immediately;
- permit cancellation;
- expose errors;
- optionally expose partial text;
- disappear quickly after insertion;
- remain usable one-handed;
- avoid accidental taps.

Do not reproduce the full application navigation inside the overlay.

---

# 35. Overlay states

Define an explicit state machine.

```text
HIDDEN

STARTING

LISTENING_EMPTY

LISTENING_WITH_PARTIAL

ENDPOINTING

FINALIZING

INSERTING

SUCCESS

CANCELLED

ERROR_MIC

ERROR_MODEL

ERROR_INSERTION

ERROR_PERMISSION
```

UI rendering must be derived from state rather than scattered booleans.

Avoid invalid combinations such as:

```text
isListening = true
isProcessing = true
hasError = true
```

without a defined visual priority.

---

# 36. Overlay shape

Recommended default is a **small floating pill**, positioned so it interferes minimally with keyboard/text content.

Concept:

```text
┌────────────────────────────┐
│ ●  Listening        ■      │
└────────────────────────────┘
```

When partial transcript is enabled:

```text
┌────────────────────────────────┐
│ ●  can you send the report…  ■ │
└────────────────────────────────┘
```

Do not create a giant waveform panel.

Waveform/audio-level feedback may be represented as a tiny responsive indicator around or near the microphone state.

The overlay should primarily tell the user:

```text
Vaani heard me.
Vaani is still listening.
I can stop/cancel.
```

---

# 37. Listening visual

Use a restrained visual state:

```text
microphone/listening indicator
+
subtle amplitude response
+
"Listening"
```

Do not create fake audio movement when the mic is silent.

The level indicator should map to real captured amplitude if available.

Motion must not become distracting over other apps.

---

# 38. Partial transcript behavior

Partial transcript should be optional.

If enabled:

- show only a short trailing window;
- do not expand indefinitely;
- do not move the target app layout;
- indicate unstable text subtly if useful;
- avoid flashing every hypothesis revision.

The user does not need to see:

```text
can
can y
can you
can you s
can you send
```

as five visually disruptive transitions.

Throttle visual updates and prefer stable prefixes.

---

# 39. Stable vs unstable text

If backend exposes stable-prefix information, visually prioritize stable tokens.

Conceptually:

```text
Can you send the report | tomor...
^^^^^^^^^^^^^^^^^^^^^^^   ^^^^^^^^
stable                    provisional
```

Do not overcomplicate typography.

A subtle opacity difference is sufficient.

Accessibility must not rely on opacity alone.

---

# 40. Stop interaction

The user should have an obvious way to stop.

Depending on invocation mode:

- release-to-stop;
- tap stop;
- repeat shortcut;
- automatic endpointing.

Do not force one behavior globally if multiple invocation modes are supported.

The UI should communicate the active method.

Example:

```text
Listening
Release to finish
```

versus:

```text
Listening
Tap ■ to finish
```

---

# 41. Cancel

Cancellation must be fast.

Possible interaction:

```text
swipe pill away
tap X
back gesture
configured invocation cancellation
```

Pick interactions consistent with actual Android implementation.

Never insert partial dictation after explicit cancellation.

Show no success animation after cancellation.

---

# 42. Finalizing state

Once speech has ended:

```text
Listening
```

should transition into something like:

```text
Finishing…
```

or a subtle processing indicator.

Do not say:

```text
Thinking…
```

Vaani is not a chatbot.

Do not use a large spinner for a 300 ms operation.

If finalization exceeds a threshold, progressively expose more status.

Example:

```text
< 1 s
subtle animated indicator only

1–3 s
"Finishing…"

> 3 s
"Taking longer than usual"
[ Cancel ]
```

Exact thresholds may be tuned from real device measurements.

---

# 43. Success state

Do not celebrate every dictation.

No confetti.

No full-screen checkmark.

Preferred:

```text
finalized text preview briefly
→ overlay fades/collapses
```

or:

```text
small check indicator for ~200–400 ms
→ disappear
```

The inserted text itself is the success feedback.

---

# 44. Insertion failure

If transcription succeeded but insertion failed, **preserve the text**.

Example:

```text
Couldn't insert text

Your dictation is safe.

"Can you send the report tomorrow?"

[ Copy ]
[ Try again ]
```

This error is important enough to expand the overlay or open a compact recovery sheet.

Never throw away a successful transcript because accessibility/IME insertion failed.

---

# 45. Microphone failure

Example:

```text
Microphone unavailable

Vaani couldn't start recording.

[ Try again ]
```

If the cause is known:

```text
Microphone permission is off.

[ Open permission settings ]
```

Do not repeatedly launch system permission pages without explicit action.

---

# 46. Offline behavior

If Vaani is intended to work offline and the local model is ready:

```text
no connection
```

should not be presented as an error.

If a required model is missing:

```text
Offline model isn't installed

Connect once to download English.
[ Download when online ]
```

Differentiate:

```text
network unavailable
```

from:

```text
model unavailable
```

---

# 47. Invocation settings UX

Invocation is central enough to deserve a dedicated setup screen.

Potential methods depend on actual implementation:

```text
Floating shortcut
Quick Settings tile
Accessibility shortcut
Keyboard integration
hardware/button shortcut where technically supported
notification action
```

Do not show methods unavailable on the device.

For each method, show:

```text
name
one-sentence behavior
setup state
test action
```

Example:

```text
Quick Settings tile
Start Vaani from anywhere using the system shade.

Status: Ready

[ Test ]
```

---

# 48. Floating shortcut

If a floating button/bubble is supported, make it optional.

The bubble must:

- be movable;
- remember position;
- avoid system gesture regions;
- avoid covering keyboard controls;
- become visually quiet when idle;
- support easy disablement.

Do not force a permanent bubble on users who prefer hardware/Quick Settings invocation.

---

# 49. Persistent notification

If Android runtime requirements demand a visible foreground-service notification, make it useful and honest.

Example:

```text
Vaani is ready

Tap to dictate

[ Dictate ] [ Pause ]
```

Do not disguise or hide mandatory system indicators.

Do not spam notification channels.

---

# 50. ONBOARDING

Onboarding should be functional and short.

Target:

```text
Welcome
↓
Choose/install model
↓
Microphone
↓
System integration/insertion permission
↓
Choose invocation
↓
Test dictation
↓
Done
```

Do not use seven marketing carousel pages before setup.

---

# 51. Welcome screen

Concept:

```text
Vaani

Speak naturally.
Get polished text anywhere.

On-device dictation built for speed,
control, and personal vocabulary.

[ Set up Vaani ]

Already configured?
[ Restore/import settings ]  // only if supported
```

One illustration/icon is enough.

Do not list fifteen features.

---

# 52. Model setup onboarding

Explain the tradeoff in user terms.

Example:

```text
Choose your dictation model

Fast English
Best for most phones
~300 MB
[ Recommended ]

Accurate English
Higher accuracy • More battery/RAM
~XXX MB
```

Only show multiple models if they actually exist.

If there is one model:

```text
Download English
Works without an internet connection after setup.
```

is better than a fake choice.

---

# 53. Permission education

Never request a permission with zero context.

Use:

```text
Microphone

Vaani needs microphone access only when you start dictating.

[ Continue ]
```

Then trigger the real Android permission sheet.

Do not create a fake permission dialog styled to look like Android.

If denied:

```text
Microphone is off

You can enable it later in Android Settings.

[ Open settings ]
[ Not now ]
```

Respect "Not now."

---

# 54. Sensitive integration permissions

Overlay/accessibility/IME-like integrations may require stronger explanation.

Explain:

- what permission enables;
- when Vaani uses it;
- what Vaani does not do, if that statement is demonstrably true;
- how to disable it.

Avoid manipulative copy.

Bad:

```text
Enable this or Vaani won't work!
```

Better:

```text
Insert text into other apps

This access lets Vaani place your finished dictation into the text field you're using.

[ Continue ]
```

Use wording that matches the actual Android capability.

---

# 55. Test dictation onboarding

Make the test demonstrate Vaani's value.

Prompt:

```text
Try saying:

"first buy milk second call Rahul third finish the report"
```

Show result:

```text
1. Buy milk
2. Call Rahul
3. Finish the report
```

Then:

```text
Looks good

[ Finish setup ]
```

If formatting/list behavior is not implemented, choose a test that matches reality.

---

# 56. Visual system

Vaani should use a restrained Material-derived visual system.

Core principles:

```text
neutral surfaces
one strong accent
high text contrast
generous but not wasteful spacing
soft component shapes
limited elevation
clear state changes
```

Do not create a card for every setting.

Use grouping, typography, dividers, whitespace, and sections.

---

# 57. Color

Default to system-aware theming.

If dynamic color is enabled:

- respect Android dynamic color;
- maintain Vaani semantic state colors;
- ensure contrast remains valid.

If a branded fallback palette is required, keep it restrained.

Recommended conceptual roles:

```text
Primary
dictation/active actions

Surface
backgrounds

Surface container
grouped controls

Success
model ready / successful setup

Warning
degraded state

Error
actual blocking failure
```

Do not color normal settings green merely because they are enabled.

Do not use error red for harmless informational states.

---

# 58. Dark theme

Dark mode must be designed, not auto-inverted.

Check:

- overlay legibility over arbitrary apps;
- contrast;
- disabled control visibility;
- input-field boundaries;
- dialog separation;
- waveform/level visibility;
- keyboard/system-bar integration.

Avoid pure black everywhere unless intentionally targeting OLED surfaces.

---

# 59. Typography

Use Android/system-friendly typography.

Hierarchy should do most visual work.

Conceptual scale:

```text
Display/large headline
rarely

Title large
screen identity

Title medium
major sections/cards

Body large
primary settings/content

Body medium
supporting text

Label
metadata/actions
```

Do not use 11 different text sizes.

Do not use all-caps section headings everywhere.

Technical strings such as paths, model identifiers, and code may use monospace selectively.

---

# 60. Spacing

Use a consistent spacing grid.

Suggested base rhythm:

```text
4 dp
8 dp
12 dp
16 dp
24 dp
32 dp
```

Common screen horizontal padding:

```text
16–20 dp compact
adaptive on larger widths
```

Do not arbitrarily use 13 dp, 19 dp, 27 dp unless required by a component.

---

# 61. Shapes

Use a small shape family rather than every component having a different radius.

Example:

```text
small   8–12 dp
medium  16 dp
large   20–28 dp
pill    full rounded
```

The dictation overlay can be pill-shaped.

Settings rows generally should not each be giant rounded cards.

---

# 62. Icons

Use a coherent icon family.

Prefer Material Symbols/icons or the project's established icon set.

Do not mix:

- outlined Material;
- random Font Awesome icons;
- emoji;
- custom 3D icons

inside the same hierarchy.

Icons must have semantic purpose.

Do not add icons to every line just to fill space.

---

# 63. Cards

Cards are for distinct grouped objects such as:

- model package;
- setup blocker;
- snippet preview;
- diagnostic event.

Do not put every settings row in an independent elevated card.

Over-cardification makes the app look like a template.

---

# 64. Motion

Motion communicates state.

Use motion for:

- overlay expansion/collapse;
- listening → finalizing;
- model-download state;
- adding/deleting list items;
- screen navigation;
- error/success acknowledgement.

Avoid decorative looping motion.

Dictation amplitude is the main justified continuous animation.

---

# 65. Haptics

Use haptics sparingly.

Potential events:

```text
dictation begins
dictation stops
explicit cancellation
critical error
successful long-press/gesture
```

Do not vibrate:

- for every partial transcript;
- for every token;
- every time punctuation changes.

Respect system haptic settings where appropriate.

---

# 66. Audio cues

Optional audio cues may distinguish:

```text
start listening
stop listening
error
```

They must be individually or globally disableable.

Do not play loud assistant-like tones.

Avoid audio cues when device/system context indicates they would be disruptive if that information is available.

---

# 67. Accessibility

Treat accessibility as implementation, not a checklist at the end.

Requirements:

- touch targets should meet Android accessibility guidance;
- screen-reader descriptions for icon-only actions;
- correct traversal order;
- no state represented only by color;
- scalable text without clipping;
- sufficient contrast;
- keyboard/switch access where relevant;
- meaningful headings;
- dynamic content announcements should not spam TalkBack;
- reduced-motion preferences should be respected where feasible.

Do not announce every partial ASR hypothesis to TalkBack.

That would be unusable.

Announce meaningful state transitions such as:

```text
Listening
Dictation complete
Microphone unavailable
```

when appropriate.

---

# 68. Large text

Test at increased font scaling.

Critical screens must not break:

- onboarding;
- model download;
- vocabulary editor;
- snippet editor;
- settings;
- overlay/recovery UI.

When text is large, allow controls to wrap vertically rather than shrinking text.

---

# 69. Adaptive layouts

On tablets/foldables:

- do not stretch a 400 dp settings column to full width;
- use sensible max widths;
- consider list-detail for vocabulary/snippets/history;
- keep forms readable;
- adapt navigation.

Example:

```text
tablet:

Vocabulary list | selected vocabulary detail
```

Phone:

```text
Vocabulary list
      ↓
detail screen
```

Do not build separate products for phone and tablet.

---

# 70. Landscape

The dictation overlay and setup flows must remain usable in landscape.

Avoid screens that assume enormous vertical space.

Bottom sheets should not cover the entire useful region unnecessarily.

---

# 71. Empty states

Every list needs a useful empty state.

Vocabulary:

```text
No custom words yet

Add names, technical terms, and words
Vaani should recognize exactly.

[ Add a word ]
```

Snippets:

```text
No snippets yet

Save spoken shortcuts for text you type often.

[ Create snippet ]
```

History:

```text
No dictations yet

Your recent dictations will appear here
if history is enabled.
```

Do not use giant illustrations that push the action below the fold.

---

# 72. Search

Vocabulary, snippets, replacements, and sufficiently large history lists need search.

Search should:

- appear when useful;
- preserve query state appropriately;
- match aliases as well as canonical values if backend supports it;
- handle empty/no-result states.

No result:

```text
No vocabulary matches "kubectl"

[ Add "kubectl" ]
```

This is an excellent contextual creation shortcut.

---

# 73. Undo

Use undo for reversible local actions:

```text
Vocabulary removed
[ Undo ]

Snippet deleted
[ Undo ]

History item deleted
[ Undo ]
```

Use confirmation instead when reversal is impossible or costly:

```text
Delete all local data
Delete downloaded model
Reset personalization
```

---

# 74. Destructive actions

Destructive buttons should not be primary-colored.

Use red/error styling only when appropriate.

Dialog copy must name the consequence.

Bad:

```text
Are you sure?
```

Good:

```text
Delete all snippets?

Your 18 saved snippets will be removed from this device.

[ Cancel ] [ Delete ]
```

---

# 75. Forms

Forms should validate inline.

Example:

```text
Spoken trigger
my GitHub

Insert
[empty]

Insert text can't be empty.
```

Do not wait until Save to reveal every basic validation failure.

Do not disable Save without explaining why when the reason is not obvious.

---

# 76. Keyboard behavior

For text-heavy personalization screens:

- use correct IME actions;
- keep save action reachable;
- scroll focused fields above keyboard;
- preserve form data through rotation/recomposition;
- don't dismiss keyboard unexpectedly;
- use monospace where appropriate for paths/code;
- allow multiline snippet values.

---

# 77. Live examples

Settings that alter formatting benefit from examples.

Example:

```text
Remove fillers      [on]

Before
"uh I think we should go"

After
"I think we should go."
```

Keep examples tiny.

Do not turn every settings page into documentation.

---

# 78. App-aware context

If Vaani obtains current-app context, make the behavior discoverable but unobtrusive.

Potential Settings explanation:

```text
App context

Use the app you're typing in to improve
formatting and vocabulary.

[ on ]
```

If deeper context such as filenames/editor symbols is supported:

```text
Developer context

Use visible editor/project terms to improve
recognition of filenames and symbols.
```

Permission disclosure must match actual collection behavior.

---

# 79. Context indicator during dictation

Do not display:

```text
Analyzing WhatsApp
Reading screen
Scanning context
```

on every invocation unless necessary.

A subtle optional indicator can show:

```text
WhatsApp • Casual
```

or:

```text
VS Code • Developer context
```

if useful.

Privacy-sensitive context access must be configurable.

---

# 80. Developer terminology UX

Technical users should be able to add entries without fighting "friendly" UI.

Vocabulary detail may optionally expose:

```text
Canonical text: calculateWER
Aliases:
- calculate W E R
- calculate wer

Type:
Code symbol
```

Paths/code must retain exact casing.

Provide copy controls where useful.

---

# 81. Model errors and diagnostics

Error UI should distinguish:

```text
model missing
model corrupted
runtime failed
out of memory
unsupported backend
download failure
checksum failure
initialization timeout
```

User-facing copy should stay simple.

Advanced detail can expose raw error/code behind:

```text
Details
```

Do not display stack traces to normal users.

---

# 82. Diagnostics screen

For development and technically advanced users:

```text
Diagnostics

STT
Model: ...
Backend: CPU
State: Ready
Last RTF: 0.24
Last finalization: 410 ms

Formatter
Model: ...
State: Ready
Last latency: 82 ms

Service
Running

Permissions
Microphone: Granted
Integration: Ready

[ Export diagnostics ]
```

This should be hidden from normal Home.

It is valuable during Vaani's development.

---

# 83. Status semantics

Create a shared status model.

Example semantic states:

```text
READY
ACTIVE
PROCESSING
PAUSED
DEGRADED
ACTION_REQUIRED
ERROR
DISABLED
```

Use consistent wording and visuals across:

- Home;
- model manager;
- overlay;
- diagnostics;
- onboarding.

Do not call the same state:

```text
Available
Ready
Loaded
Online
Active
```

in five different screens unless meanings differ.

---

# 84. Copywriting

Copy should be short and concrete.

Prefer:

```text
Add a word
```

over:

```text
Enhance your personalized vocabulary experience
```

Prefer:

```text
Download model
```

over:

```text
Initialize AI language intelligence
```

Prefer:

```text
Listening
```

over:

```text
Vaani is intelligently processing your voice
```

No anthropomorphic "I'm thinking" language.

---

# 85. Product terminology

Use these terms consistently:

```text
Dictation
Vocabulary
Snippet
Replacement
Writing style
Model
Language
History
Correction
Listening
Finishing
```

Avoid interchangeable labels such as:

```text
Custom dictionary
Personal glossary
Vocabulary memory
Word intelligence
```

for the same feature.

Choose one product term and stick to it.

---

# 86. Do not expose ML internals unnecessarily

Normal UI should not contain:

```text
beam width
temperature
logit score
BPE
CTC
RNNT
Zipformer
INT4
KV cache
decoder confidence
```

unless the feature is explicitly inside Advanced/Diagnostics.

A technically sophisticated backend does not require a technically cluttered UX.

---

# 87. Confidence UX

If recognition confidence is available, do not paint every word red/yellow/green.

Confidence should primarily drive behavior internally.

Only surface uncertainty when the user needs to act.

Example:

```text
Did you mean "Hyprland"?

[ Hyprland ] [ hyper land ]
```

Use sparingly.

Constant uncertainty highlighting makes dictation feel unreliable.

---

# 88. Correction suggestions

When the system is uncertain about a critical term:

```text
CUDA
Coda
Quda
```

present alternatives only if:

- ambiguity is meaningful;
- confidence is low;
- choosing matters;
- automatic safe resolution failed.

Do not interrupt every sentence.

---

# 89. First-run success metric

Onboarding succeeds when the user has:

```text
required model ready
+
microphone ready
+
system text insertion ready
+
one invocation method ready
+
completed one successful test dictation
```

Do not mark setup "complete" merely because the user reached the last page.

---

# 90. Daily-use success metric

A normal returning user should be able to dictate without opening the full app.

That is the key UX acceptance criterion.

---

# 91. Progressive disclosure

Keep the default UI simple.

Example:

```text
Performance
Balanced
```

tap:

```text
Battery saver
Balanced
Fastest

Advanced runtime options >
```

Do not display:

```text
Threads: 6
Provider: XNNPACK
INT8 activation
chunk size
```

next to the basic preset.

---

# 92. Loading states

Use skeletons only for content that genuinely loads asynchronously and benefits from spatial placeholders.

Do not use skeleton cards for local settings that should be instant.

Model initialization should use meaningful status.

Example:

```text
Loading English model…
```

If loading is routine and brief, keep it subtle.

---

# 93. App startup

Opening Vaani should not display a splash longer than necessary.

Use the Android splash-screen mechanism consistent with platform expectations.

Do not add an extra fake splash Activity afterward.

Home should appear even if the model is still initializing.

Represent runtime initialization as state inside Home.

---

# 94. State persistence

UI should survive:

- rotation;
- activity recreation;
- process recreation where practical;
- navigation away/back;
- permission-sheet round trips;
- model download while app is backgrounded.

Do not reset an in-progress snippet form because a permission sheet opened.

---

# 95. Model download resilience

Downloads should handle:

- app backgrounding;
- network loss;
- pause/retry;
- storage failure;
- verification;
- app restart.

UI must reconnect to actual download state rather than starting a second apparent download.

---

# 96. Permission state refresh

After returning from Android Settings, re-check permission/state.

Do not assume the user enabled the permission because they opened Settings.

Update UI immediately.

---

# 97. Notification/overlay privacy

Never show sensitive full dictated text in a lock-screen notification by default.

If the overlay appears over other apps, avoid lingering final text longer than needed.

Provide privacy settings if history/preview behavior is configurable.

---

# 98. Screenshot and screen-record behavior

Do not arbitrarily block screenshots across the entire app.

If screens can contain sensitive history/snippet content, determine whether the product wants optional secure-window behavior.

Do not enable it globally without product justification because it interferes with support/debugging.

---

# 99. Analytics and telemetry

Do not add telemetry merely for UI redesign.

If analytics already exists:

- respect current privacy architecture;
- do not log raw dictated text;
- do not log snippet values;
- do not log vocabulary content unless explicitly designed, disclosed, and justified.

UI event analytics should use semantic events, not private content.

---

# 100. Accessibility service trust UX

If Vaani relies on AccessibilityService, this is a trust-critical screen.

The explanation must be precise.

Explain only actual capabilities.

Example structure:

```text
Use Vaani in other apps

Vaani uses Android accessibility integration to
place finished dictation into the text field you're
currently using.

What Vaani uses it for
• finding the active text field
• inserting your finished dictation

[ Continue ]
```

ONLY claim those bullets if implementation actually restricts itself accordingly.

Add:

```text
Why is this needed?
```

for deeper explanation.

Do not use fear or urgency.

---

# 101. Accessibility service off state

If user disables it later:

```text
Text insertion is off

Dictation can still be tested inside Vaani,
but Vaani can't insert text into other apps.

[ Re-enable ]
```

Preserve the distinction between STT functionality and integration functionality.

---

# 102. Quick Settings tile

If supported:

Tile states should be immediately understandable.

Examples:

```text
Vaani
Ready

Vaani
Listening

Vaani
Paused
```

Tapping should have one predictable action.

Do not overload single/double/long tap without strong justification.

Long press can open app/settings following Android expectations.

---

# 103. Widget

Do not prioritize a home-screen widget for V1 unless evidence shows it improves invocation.

A Quick Settings tile / overlay / keyboard/integration shortcut is generally more relevant to system-wide dictation than a decorative widget.

---

# 104. Voice waveform

Do not let waveform aesthetics dictate product design.

If included:

- compact;
- real amplitude;
- low visual noise;
- 30/60 fps only if inexpensive;
- stop animation immediately on stop;
- reduce update frequency in battery-saving mode if necessary.

No fake studio waveform filling half the screen.

---

# 105. Latency-aware UI

UI must be designed around actual backend timing.

Instrument these milestones:

```text
invocation requested
microphone opened
first audio frame
first partial transcript
speech endpoint detected
final ASR ready
formatter ready
replacement/snippet complete
insertion requested
insertion confirmed
overlay dismissed
```

Use these timestamps to tune UX.

Do not hide a 2-second backend delay under longer animations.

Animation must never intentionally increase completion latency.

---

# 106. Perceived latency

Useful techniques:

- immediate listening acknowledgement;
- continuous partial result;
- stable-prefix display;
- finalization transition;
- optimistic overlay collapse only after text is safe;
- keep expensive initialization warm where backend/product permits.

Never show "Done" before text is safely available.

---

# 107. Battery-aware UX

If a mode keeps models resident and measurably affects battery:

```text
Keep Vaani ready
Faster starts, slightly higher memory/battery use.
```

Provide an understandable tradeoff.

Do not expose meaningless battery percentages without measurement.

---

# 108. Thermal degradation

If runtime detects severe degradation and supports changing mode:

```text
Vaani is running slower because the device is warm.

[ Use balanced mode ]
```

This is advanced behavior, not required for first implementation.

Do not invent thermal warnings without sensor/runtime evidence.

---

# 109. Personalization import/export

If supported:

Export should produce a clear bundle of:

```text
vocabulary
snippets
replacements
styles
```

Never export history/audio by default unless explicitly selected.

Import must preview conflicts.

Example:

```text
Import personalization

24 vocabulary entries
6 snippets
3 replacements

2 conflicts

[ Review conflicts ]
[ Import ]
```

---

# 110. Search + add shortcut

When a user searches vocabulary and finds nothing:

```text
No matches

[ Add "Hyprland" ]
```

When searching snippets:

```text
No snippet named "work email"

[ Create "work email" ]
```

Use context to reduce steps.

---

# 111. Personalization counts

Counts can be useful:

```text
Vocabulary  24
Snippets     6
```

Do not turn them into analytics KPI cards.

No pie charts.

No "productivity score."

---

# 112. History metrics

Do not prioritize:

```text
words spoken today
hours saved
productivity percentage
streak
```

unless product evidence shows users want it.

Vaani is a utility, not a gamified habit tracker.

---

# 113. Open-source considerations

Because Vaani is intended to be open-source:

- avoid proprietary design assets unless licensing is clear;
- use reproducible icons/fonts/assets;
- keep design tokens in code;
- document nonstandard components;
- make feature flags explicit;
- make model/license information accessible in About/Models.

Do not copy Wispr Flow assets, trademarks, illustrations, animations, or exact layouts.

Copy **capability ideas**, not protected visual identity.

---

# 114. About screen

Include:

```text
Vaani
version

Local voice dictation

Open-source licenses
Model licenses
Privacy
GitHub
Report a problem
Diagnostics
```

Only include links/routes that actually exist.

---

# 115. Error reporting

If "Report a problem" exists, prefill technical diagnostics only with user approval.

Never silently attach raw dictation, snippets, vocabulary, or audio.

Example:

```text
Include technical diagnostics
✓ app version
✓ device/runtime
✓ model version
✗ dictated text
✗ personal vocabulary
```

---

# 116. Component architecture

If using Compose, build reusable components around product semantics rather than screen-specific copies.

Examples:

```text
VaaniTopBar
VaaniSettingRow
VaaniSection
VaaniStatusChip
ModelCard
PermissionCard
VocabularyRow
SnippetRow
ReplacementRow
EmptyState
ErrorState
InlineBanner
DictationPill
AudioLevelIndicator
DownloadProgress
DangerZone
```

Do not create a massive universal component with 25 booleans.

Favor small composable APIs.

---

# 117. Design tokens

Centralize:

```text
colors
typography
shapes
spacing
elevation
motion durations
```

Do not hard-code arbitrary colors/radii/padding throughout screens.

Semantic tokens may include:

```text
dictationActive
statusReady
statusWarning
statusError
protectedText
overlaySurface
```

They should resolve appropriately in light/dark/dynamic themes.

---

# 118. Preview/test states

Every major component should be previewable/testable in important states.

Especially:

```text
DictationPill:
idle
listening
partial
finalizing
error

ModelCard:
not installed
downloading
ready
failed

PermissionCard:
required
granted
denied

Vocabulary:
empty
populated
search-no-result
```

Do not require a live model to visually test the entire UI.

---

# 119. UI state architecture

Prefer immutable screen state.

Concept:

```kotlin
data class HomeUiState(
    val readiness: Readiness,
    val modelState: ModelState,
    val integrationState: IntegrationState,
    val vocabularyCount: Int,
    val snippetCount: Int,
    val isLoading: Boolean,
    val error: UiError?
)
```

The exact architecture should follow the repository.

The principle is:

```text
backend/service state
      ↓
view model/state holder
      ↓
single coherent UI state
      ↓
render
```

not imperative view mutation scattered through callbacks.

---

# 120. Dictation state architecture

Dictation deserves its own explicit model.

Conceptually:

```text
Hidden

Starting

Listening(
  partialText,
  stablePrefix,
  audioLevel
)

Finalizing(
  text
)

Insertion(
  text
)

Success

Failure(
  stage,
  recoverableText,
  action
)
```

This will reduce overlay bugs.

---

# 121. Navigation behavior

Navigation should:

- preserve scroll where expected;
- use back predictably;
- avoid nested back stacks for tiny bottom sheets;
- deep-link from notifications/settings when useful;
- return from edit screens to the expected list;
- support system back.

Do not intercept Back globally to show custom confirmation unless unsaved work would be lost.

---

# 122. Unsaved form behavior

For snippet/vocabulary edits:

If the user changed data and presses back:

- auto-save only if product explicitly chooses that model;
- otherwise ask only when meaningful changes would be lost.

Avoid confirmation if the form is untouched.

---

# 123. Bottom sheets

Use bottom sheets for short focused tasks:

- quick add vocabulary;
- quick correction;
- choose style;
- simple filter.

Use full screens for:

- long snippet editing;
- multi-step permissions;
- model management;
- advanced settings;
- detailed diagnostics.

Do not put a 12-field form in a half-height sheet.

---

# 124. Dialogs

Dialogs are for decisions, not information dumps.

Good:

```text
Delete English model?

Offline dictation won't work until you download it again.

[ Cancel ] [ Delete ]
```

Bad:

A four-paragraph tutorial in a modal.

---

# 125. Snackbar/toast policy

Prefer Snackbar for reversible app actions.

Use Toast sparingly.

Do not show both for the same action.

Examples:

```text
Snippet saved
```

does not necessarily need any transient feedback if navigation/state already proves it.

```text
Snippet deleted [Undo]
```

benefits from Snackbar.

---

# 126. User testing scenarios

The agent must manually walk through at least these scenarios.

### Scenario A — first install

```text
fresh app
→ model missing
→ microphone denied initially
→ user grants later
→ integration setup
→ invocation setup
→ successful test
```

### Scenario B — normal dictation

```text
invoke
→ listen
→ partial
→ endpoint
→ final
→ insert
```

### Scenario C — cancel

```text
invoke
→ speak
→ cancel
→ no text inserted
```

### Scenario D — insertion failure

```text
ASR succeeds
→ insertion fails
→ transcript remains recoverable
→ copy/retry
```

### Scenario E — vocabulary

```text
search Hyprland
→ no match
→ add
→ alias "hyper land"
→ save
→ immediately appears
```

### Scenario F — snippet

```text
create "my GitHub"
→ URL
→ test
→ edit
→ delete
→ undo
```

### Scenario G — model failure

```text
model corrupted/unavailable
→ clear next action
→ recover
```

### Scenario H — permission revoked

```text
working app
→ integration permission revoked externally
→ return
→ state updates
→ repair path
```

### Scenario I — dark mode + large font

Complete core workflow without clipping or inaccessible controls.

### Scenario J — offline

No internet, model installed:
dictation remains normal.

---

# 127. Performance testing of UI

Do not allow the UI to become the bottleneck.

Measure:

- cold screen render;
- overlay first-frame time;
- overlay update cost during partial transcription;
- waveform/audio indicator cost;
- scrolling large vocabulary/snippet lists;
- recompositions if Compose;
- memory impact of history lists.

Do not recompose an entire overlay tree for every audio sample.

Throttle visual audio-level updates independently from model audio processing.

---

# 128. Large lists

Vocabulary/history may grow.

Use lazy/recycled lists.

Do not render thousands of rows eagerly.

Search/filter should avoid blocking the main thread.

---

# 129. Animations and model inference

UI animation and STT inference may compete for CPU/GPU resources on low-end devices.

Keep overlay animation inexpensive.

Avoid:

- blur-heavy layers;
- full-screen shaders;
- complex particle effects;
- giant continuous vector animations.

Dictation accuracy/latency has priority over decoration.

---

# 130. Low-end device principle

The interface must remain responsive while local inference is active.

If tradeoffs are necessary:

```text
drop decorative animation first
```

not:

```text
delay stop button response
```

Interaction controls must remain responsive during CPU-heavy inference.

---

# 131. Privacy-first defaults

Where product requirements permit:

- history should have explicit retention;
- avoid retaining audio unnecessarily;
- hide sensitive previews from lock screen;
- make data deletion straightforward;
- separate personalization from history;
- disclose online processing if it exists.

Do not turn privacy into marketing if technical behavior does not support the claim.

---

# 132. V1 scope discipline

Prioritize V1 UI in this order:

```text
P0
onboarding
model readiness
permissions/integration
invocation
dictation overlay
error recovery
basic settings

P1
vocabulary
snippets
replacements
privacy/data management
diagnostics

P2
history
correction teaching
per-app styles
import/export

P3
advanced contextual/developer UX
multiple models/languages
adaptive tablet list-detail polish
```

Adjust priority only when repository capability makes another ordering clearly more rational.

Do not spend a week polishing History while overlay insertion still has broken UX.

---

# 133. What must NOT be redesigned casually

Do not alter these without evidence/reason:

- model pipeline;
- STT training;
- formatter training;
- vocabulary matching semantics;
- snippet semantics;
- safety boundary;
- backend service lifecycle;
- persistent data format.

This directive is for UI/UX.

If UI reveals a backend architecture flaw, document it separately rather than silently refactoring unrelated ML/runtime code.

---

# 134. Visual QA checklist

Before considering a screen complete, verify:

```text
[ ] clear primary action
[ ] no unnecessary card nesting
[ ] light mode
[ ] dark mode
[ ] dynamic color if supported
[ ] long text
[ ] large font
[ ] narrow phone
[ ] landscape
[ ] tablet/adaptive width where required
[ ] keyboard open
[ ] empty state
[ ] loading state
[ ] error state
[ ] offline state where relevant
[ ] TalkBack/content descriptions
[ ] touch targets
[ ] system bar/inset handling
```

---

# 135. Dictation QA checklist

```text
[ ] instant visual acknowledgement
[ ] mic-open state accurate
[ ] real audio level
[ ] partial text throttled
[ ] stable text not excessively flashing
[ ] explicit stop
[ ] explicit cancel
[ ] cancel never inserts
[ ] finalizing state exists
[ ] no fake progress
[ ] successful insertion dismisses quickly
[ ] insertion failure preserves transcript
[ ] permission failure gives repair action
[ ] model failure gives repair action
[ ] overlay does not obstruct keyboard excessively
[ ] works in light target app
[ ] works in dark target app
[ ] remains readable over visually busy apps
[ ] accessibility labels
[ ] motion inexpensive
```

---

# 136. Design review artifacts

Before implementing the entire redesign, produce:

```text
docs/ui-ux/
  INFORMATION_ARCHITECTURE.md
  USER_FLOWS.md
  SCREEN_INVENTORY.md
  STATE_MATRIX.md
  DESIGN_TOKENS.md
  ACCESSIBILITY.md
```

Also provide screenshots/previews for:

1. Home ready;
2. Home setup-blocked;
3. Personal vocabulary;
4. add vocabulary;
5. snippets;
6. add/edit snippet;
7. replacements;
8. Settings root;
9. model manager;
10. privacy/data;
11. onboarding permission;
12. onboarding test;
13. dictation overlay listening;
14. dictation overlay partial;
15. dictation overlay finalizing;
16. insertion failure recovery;
17. dark-theme equivalents of critical surfaces.

Do not implement 20 inconsistent screens before validating the shared design system.

---

# 137. Implementation sequence

Use this order.

## Phase 1 — discovery

Inspect repository and backend capabilities.

Deliver:

```text
UI_UX_BASELINE.md
SCREEN_INVENTORY.md
STATE_MATRIX.md
```

No broad redesign yet.

## Phase 2 — foundations

Implement/clean:

```text
theme
colors
typography
shapes
spacing
shared components
navigation shell
UI state patterns
```

## Phase 3 — dictation core

Implement:

```text
overlay state machine
listening surface
partial transcript
finalizing
success
cancel
errors
recovery
```

This is higher priority than decorative Home work.

## Phase 4 — setup

Implement:

```text
onboarding
model state
permissions
integration
invocation setup
test dictation
```

## Phase 5 — control center

Implement:

```text
Home
Personalize
Vocabulary
Snippets
Replacements
Settings
Models
Privacy
Diagnostics
```

## Phase 6 — secondary UX

Only where backend supports it:

```text
History
Corrections
App styles
Import/export
Developer context
```

## Phase 7 — QA

Run:

```text
accessibility
large font
dark/light
offline
permission revocation
process recreation
rotation
low-end performance
overlay stress testing
```

---

# 138. Agent behavior during implementation

The implementing agent must:

1. inspect before rewriting;
2. preserve working backend behavior;
3. use existing project conventions where sensible;
4. build reusable product-level components;
5. implement real states rather than screenshots;
6. avoid hard-coded fake values;
7. keep screens connected to state;
8. test navigation;
9. test permissions on device/emulator;
10. document backend gaps instead of faking them;
11. keep compilation/tests passing at meaningful checkpoints;
12. avoid huge one-shot rewrites that are impossible to debug.

After each major phase, record:

```text
what changed
what was tested
what remains
known backend blockers
screenshots/previews
```

---

# 139. Definition of "premium"

Do not interpret "premium" as:

```text
more gradients
more shadows
more animations
more glass
more cards
```

For Vaani, premium means:

```text
nothing ambiguous
nothing visually accidental
fast state response
beautiful typography
consistent geometry
excellent dark mode
excellent haptics
smooth but restrained motion
clear recovery
no dead controls
no clutter
```

---

# 140. Definition of "minimal"

Minimal does NOT mean removing useful information.

Bad minimalism:

```text
microphone icon
nothing else
```

when the user does not know if the model is ready.

Good minimalism:

```text
Ready
English • On-device

[ Test dictation ]
```

Every visible element should answer a user question or enable an action.

---

# 141. Definition of "native"

Native does not mean visually bland.

It means Vaani should respect:

- Android navigation;
- system permission flows;
- back behavior;
- typography/scaling;
- dynamic color where appropriate;
- system bars;
- haptics;
- notifications;
- adaptive layouts;
- accessibility;
- platform interaction expectations.

Custom branding sits **on top of** these conventions rather than fighting them.

---

# 142. Final product test

Ask:

> If Vaani's full-screen app disappeared after setup, could the user still understand and successfully use dictation every day?

If no, the dictation invocation/overlay experience is too dependent on the app.

Then ask:

> If something breaks, can the user open Vaani and understand exactly what needs attention?

If no, the control center is too minimal or too technical.

Both conditions must be true.

---

# 143. Deliverables required from the agent

Do not return only design commentary.

Deliver:

1. repository UI/UX audit;
2. feature-capability matrix;
3. information architecture;
4. user-flow diagrams in Markdown/Mermaid or equivalent;
5. screen/state inventory;
6. design-token specification;
7. navigation implementation;
8. shared component implementation;
9. dictation overlay implementation;
10. onboarding implementation;
11. Home implementation;
12. Personalize/Vocabulary implementation;
13. Snippets implementation;
14. Replacements implementation;
15. Settings/model/privacy implementation;
16. diagnostics UI;
17. supported History/App-style UI if backend exists;
18. accessibility review;
19. screenshots/previews;
20. build/test results;
21. list of backend blockers;
22. final UX acceptance checklist.

---

# 144. Final directive

Do not build Vaani as a screen the user visits in order to speak.

Build it as a **system-wide dictation capability** that has an Android app for setup, control, personalization, recovery, and trust.

The most important visual hierarchy in the project is not the Home screen.

It is:

```text
INVOKE
   ↓
LISTEN
   ↓
UNDERSTAND
   ↓
FINALIZE
   ↓
INSERT
   ↓
DISAPPEAR
```

Every UI decision should make that path faster, clearer, safer, and less intrusive.

When there is a conflict between visual spectacle and dictation responsiveness:

**responsiveness wins.**

When there is a conflict between aggressive automation and preserving the user's words:

**preservation wins.**

When there is a conflict between exposing every technical capability and keeping the default experience understandable:

**progressive disclosure wins.**

When a backend feature does not exist:

**truthfulness wins.**

That is the Vaani Android UX.


---

# 145. Brand image system and visual-asset direction

The previous sections define product behavior and interface structure. This section defines how the agent should approach **brand imagery**, illustrations, supporting visuals, screenshots, and visual atmosphere for Vaani.

The goal is not to create random marketing art. The goal is to create a **coherent image system** that supports the product's identity.

Vaani is a local-first dictation tool. Its brand imagery should communicate:

- clarity;
- calmness;
- privacy;
- intelligence without sci-fi clichés;
- warmth without childishness;
- precision;
- speed;
- flow;
- trust.

The uploaded reference image suggests a useful emotional direction:

- warm golden-hour light;
- calm atmosphere;
- quiet motion;
- human-scale perspective;
- soft depth;
- premium natural mood;
- a sense of movement and flow rather than aggression.

Use that image as **mood inspiration**, not as a literal UI background to copy.

---

# 146. What Vaani brand imagery should feel like

The brand image system should feel:

```text
warm
soft
focused
human
fluid
clean
quietly premium
```

It should not feel:

```text
cold enterprise
hard cyberpunk
overly futuristic
noisy
hyper-saturated
gimmicky
robotic
stock-photo-generic
```

Do not use obvious AI tropes like:

- floating holograms;
- blue neon brains;
- circuit patterns on faces;
- robot heads;
- glowing microphones everywhere;
- sci-fi grids;
- "AI magic" spark particles;
- fake waveform walls.

The images should support a product that helps words move naturally from speech to text.

---

# 147. Brand image categories

The agent should design the image system in clear categories.

## 147.1 Hero / marketing images

Used for:

- onboarding welcome screens;
- landing page headers;
- Play Store screenshots if needed;
- internal docs/mockups;
- app promo assets.

These can be more atmospheric and emotional.

## 147.2 Product-support illustrations

Used for:

- empty states;
- permissions explanations;
- offline/model download screens;
- privacy screens;
- no-history states;
- vocabulary/snippet onboarding.

These must remain simple and secondary to content.

## 147.3 Functional product visuals

Used for:

- app icons;
- feature icons;
- chips/badges;
- screenshots;
- model cards;
- quick how-it-works diagrams.

These must prioritize readability over mood.

## 147.4 Social/brand media visuals

Used for:

- GitHub README banners;
- release cards;
- teaser posts;
- feature announcement cards.

These can be more graphic, but still must stay within the same brand language.

---

# 148. How to use the uploaded reference image

The uploaded reference image should influence the following aspects:

```text
lighting
tone
emotional temperature
sense of motion
softness
premium calmness
```

It should NOT force:

```text
same composition
same person
same environment
same city skyline
same literal photograph
```

Extract the mood:

- warm sunlight;
- natural green surroundings;
- soft cinematic blur;
- a path/flow metaphor;
- quiet forward movement.

Translate that into Vaani brand visuals as:

- flowing paths/lines;
- soft layered shapes;
- warm sunlight gradients;
- subtle motion direction;
- calm human moments;
- spatial openness.

---

# 149. Core art direction

Prefer an image language made from:

- soft gradients;
- diffused light;
- layered translucent shapes;
- subtle shadows;
- gentle depth;
- clean geometry;
- abstract path/flow motifs;
- soft-edged illustrative environments;
- minimal human-presence cues where useful.

You may combine:

```text
abstract illustration
soft editorial-style scenes
minimal UI-combined mockups
```

Do not combine too many visual languages at once.

One coherent language is better than five trendy ones.

---

# 150. Human presence in brand images

Vaani may include human presence, but carefully.

Allowed directions:

- back-view or side-view human figures;
- hands holding a phone;
- simple editorial lifestyle framing;
- abstracted or minimally detailed humans;
- silhouettes or reduced-detail figures in supportive scenes.

Avoid:

- exaggerated emotional facial portraits;
- cheesy "business people smiling at laptop" stock-photo energy;
- idol-like beauty shots;
- hyper-real influencer imagery;
- crowds;
- dramatic acting.

The person should support the idea of natural communication and motion, not dominate the brand.

If an image includes a person, the product remains the subject.

---

# 151. Illustration style

Preferred illustration characteristics:

```text
flat or softly dimensional
minimal detail
clean contours
organic curves
subtle depth
mature color control
limited texture
```

Illustrations should feel closer to:

- premium productivity apps;
- thoughtful editorial tech products;
- calm digital wellbeing products;

and not like:

- children's ed-tech;
- gaming banners;
- crypto startups;
- futuristic AI poster art.

Use simplified elements such as:

- speech-flow ribbons;
- path motifs;
- layered cards;
- abstract text fragments;
- calm environmental forms;
- light beams;
- sunlit surfaces;
- minimal greenery or natural cues.

---

# 152. Photography direction

If photography is used, it should follow these rules:

- warm natural light;
- soft focus or depth-of-field where appropriate;
- calm candid framing;
- uncluttered environments;
- visually quiet scenes;
- premium but real;
- clean clothing/styling if people are present.

Avoid:

- obvious office stock imagery;
- headset call-center imagery;
- staged meetings;
- harsh artificial lighting;
- neon tech scenes;
- sterile white-cyclorama product shots unless needed.

Photography should feel like a human world where dictation naturally fits.

---

# 153. Backgrounds and ambient visuals

Background artwork should be low-noise.

Good directions:

- soft warm gradients;
- subtle sunlit shadows;
- abstract path lines;
- blurred foliage/light atmosphere;
- layered shape compositions;
- calm horizon-like compositions.

Bad directions:

- dense patterns;
- busy line art;
- multiple focal points;
- heavy texture noise;
- overly dark backgrounds behind small text;
- dramatic high-contrast photography behind UI.

Backgrounds must not fight interface content.

---

# 154. Product mockups in brand images

When creating product images, prefer showing:

- the dictation pill overlay;
- a clean Android screen with a text field;
- before/after dictation examples;
- snippet/vocabulary personalization;
- a calm, polished UI context.

Do not create fake UI that contradicts the actual app.

Brand mockups must remain aligned with the real design system.

The agent should reuse real UI components/screenshots whenever possible rather than painting fantasy product screens.

---

# 155. Image color system

Brand images should derive from the app color system and mood, not invent a separate palette.

Image colors should generally lean toward:

- warm neutrals;
- soft gold/sunlight accents;
- muted greens if nature references are used;
- calm surface tones;
- one clear product accent.

Avoid overusing saturated rainbow color.

The product accent should remain recognizable but not overpowering.

Possible tonal structure:

```text
Base neutral surface
Warm cream / stone / soft graphite

Accent
warm amber / golden / subtle coral / muted teal depending brand choice

Secondary support
soft green / muted olive / cool gray only where needed
```

Exact values should come from the established design tokens, not from random image generation choices.

---

# 156. Light and contrast rules for images

Every brand image should preserve legibility for overlaid text.

Therefore:

- reserve calm negative space;
- avoid placing text over detailed focal areas;
- use soft vignettes/gradient fades where appropriate;
- keep high-contrast focal details away from UI copy blocks.

The image system should support layouts such as:

```text
left-aligned headline over quiet area
right-side product mockup
bottom call-to-action
```

or

```text
centered message with abstract background
```

The image must serve layout.

---

# 157. Specific asset guidelines

## 157.1 Onboarding artwork

Onboarding images should be:

- simple;
- readable at phone scale;
- metaphorical rather than literal;
- optimized for small displays.

Potential metaphors:

- speech becoming clean text;
- a flowing path becoming organized lines;
- a quiet beam or ribbon connecting voice and words;
- natural movement guiding scattered fragments into structure.

Do not use dense scenes on onboarding pages.

## 157.2 Empty-state artwork

Empty-state illustrations must be subtle and lightweight.

Examples:

- no history;
- no snippets;
- no vocabulary entries;
- no models downloaded.

These visuals should support the action, not become the action.

## 157.3 Diagnostics or technical screens

Do not add decorative illustrations to technical/diagnostic screens unless they help comprehension.

## 157.4 Model management screens

A simple package/download iconography is often enough.

No need for a big AI-themed hero.

---

# 158. Iconography for brand and feature images

Icons should align with the UI system.

Use:

- simple line/filled icons;
- consistent stroke/weight;
- rounded or gently geometric forms;
- clear metaphors.

Possible feature icons:

```text
Vocabulary -> text/quote + sparkle-free word cue
Snippets -> text expansion
Replacements -> transform/swap text
History -> clock
Privacy -> shield/lock
Model -> chip/package/download
Dictation -> microphone
Styles -> palette/text-format
```

Avoid novelty icons that break consistency.

---

# 159. Typography inside brand images

Text rendered inside brand images must match the product voice:

- concise;
- direct;
- high contrast;
- no long paragraphs;
- no fake futuristic fonts;
- no decorative cursive or novelty type.

If text appears in an image:

- it should follow the same hierarchy logic as the app;
- it should remain readable at mobile size;
- it should use the same brand tone as the UI copy.

Do not use images as an excuse to ignore typography discipline.

---

# 160. Brand-image anti-patterns

Explicitly avoid:

```text
3D chrome logos
glowing microphone orbs
AI brain imagery
blue-purple neon blobs
random lens flares
stock business teams
floating UI cards everywhere
crowded collage posters
meme aesthetics
anime mascots unless deliberately adopted later
hyper-minimal emptiness with no meaning
```

Also avoid copying another brand's image system too closely.

The point is to build Vaani's own calm, precise visual identity.

---

# 161. Process for generating or commissioning images

The agent should follow this sequence for any new brand image:

1. Identify the asset type:
   - onboarding;
   - hero;
   - empty state;
   - social card;
   - product mockup;
   - feature visual.

2. Identify the communication goal:
   - explain;
   - reassure;
   - inspire;
   - direct action;
   - show capability.

3. Decide whether the asset should be:
   - abstract;
   - illustrative;
   - photographic;
   - UI-led;
   - mixed.

4. Keep one focal idea only.

5. Ensure the image leaves room for text/content if used in layout.

6. Verify it matches:
   - warmth;
   - calm precision;
   - local-first trust;
   - product realism.

7. Check against anti-pattern list.

The agent must not generate "pretty art" disconnected from product use.

---

# 162. Screenshots for store/listing/marketing

If the agent designs screenshots or marketing panels:

- use real UI or high-fidelity UI based on the actual design system;
- keep one message per panel;
- do not overload with seven bullet points;
- use clear, honest captions;
- show product flow;
- show personalization as a differentiator;
- show that Vaani works across apps.

Recommended screenshot story:

```text
1. Speak naturally anywhere
2. Get clean, formatted text
3. Teach Vaani your words
4. Save snippets and replacements
5. Stay local and in control
```

Do not claim unsupported features.

---

# 163. Keyboard layout and keyboard-adjacent UX

The Android keyboard relationship is critical for Vaani.

The agent must make a deliberate decision about **how Vaani appears when the user is typing**.

Vaani should be treated as a dictation layer that coexists with the system keyboard, not as a full-screen takeover.

Core rule:

> The user should be able to invoke Vaani while focusing a text field, with minimal disruption to the keyboard workflow.

This means the agent must explicitly design:

- where the dictation pill/overlay sits when the keyboard is open;
- whether the keyboard remains visible;
- how the overlay avoids covering keys;
- how insertion occurs;
- how cancel/retry works;
- how one-handed use works.

---

# 164. Default keyboard coexistence strategy

Preferred default behavior:

```text
Text field focused
    ↓
Keyboard visible
    ↓
Vaani invoked
    ↓
Compact dictation pill appears ABOVE the keyboard or in a safe floating position
    ↓
User speaks
    ↓
Text inserted into active field
    ↓
Overlay disappears
```

This is better than:

```text
Vaani invoked
→ keyboard hides
→ full-screen recorder opens
→ user loses context
```

unless platform restrictions force a fallback path.

The user should keep visual context of what they are writing.

---

# 165. Keyboard visibility policy

The app should define clear behavior for these cases.

## Case A — keyboard open, text field focused

Prefer keeping the keyboard visible unless:

- it physically conflicts with the dictation UI;
- the current invocation method inherently replaces it;
- the underlying Android integration makes this impossible.

## Case B — text field focused, keyboard hidden

Vaani may still show the dictation overlay and insert into the active field.

## Case C — no editable field detected

Vaani should not pretend it can insert text.

Show a helpful state such as:

```text
No text field selected

Tap into a text field, then try again.
```

Do not record a full dictation and fail silently later.

---

# 166. Dictation pill placement relative to keyboard

Preferred positions, in order:

1. **Above the keyboard**, centered or aligned to avoid important IME controls.
2. **Floating near the bottom but not overlapping the keyboard suggestion row or action row.**
3. **A movable floating position remembered by the system** if persistent overlay mode exists.

The overlay must not cover:

- space bar;
- return/send key;
- mic/search/send key row;
- emoji switch;
- suggestion row;
- predictive text strip where possible;
- system navigation gestures.

It must also avoid blocking the active cursor area excessively.

---

# 167. Keyboard-aware safe zones

When the keyboard is visible, the agent should define safe layout zones.

Conceptually:

```text
Top content area
--------------------------------
text field / app content
--------------------------------
safe overlay band
--------------------------------
keyboard suggestion row
keyboard keys
system nav area
```

The dictation pill should live in the **safe overlay band**, not on top of the typing keys.

If the phone is small, the pill may need to reduce width or simplify content.

---

# 168. Dictation UI compactness when keyboard is present

When the keyboard is open, the overlay must become even more compact.

Allowed elements:

- listening indicator;
- short status label;
- stop/cancel;
- a short partial-text preview if enabled.

Avoid while keyboard is present:

- long transcript cards;
- help text paragraphs;
- large waveform;
- multi-button toolbars;
- explanatory banners.

The keyboard context demands visual discipline.

---

# 169. Partial transcript behavior with keyboard open

If partial transcript is shown while the keyboard is visible:

- keep it to one line or a very short two-line maximum;
- fade or clip old content;
- avoid resizing the overlay dramatically;
- never cover so much vertical space that the user loses their original message context.

The user is still composing text. Do not push the text field out of mental focus.

---

# 170. Editing and insertion behavior

After dictation completes, Vaani should insert text relative to the cursor or selection in a predictable way.

Key rules:

- insert at current cursor if no selection exists;
- replace current selection if text is selected;
- preserve surrounding text spacing correctly;
- avoid duplicate spaces;
- respect line breaks if formatter output contains lists/paragraphs;
- avoid moving cursor unpredictably.

If insertion fails, preserve the formatted text for copy/retry.

The user must never lose their dictated result.

---

# 171. Keyboard send/action coordination

In messaging contexts, the keyboard often includes a send button.

Vaani must not automatically send messages unless the product very explicitly implements and discloses such a feature.

Default rule:

> Vaani inserts text only. It does not submit/send by default.

This is a usability and safety decision.

Users should be able to review text before sending.

---

# 172. One-handed usability

The keyboard interaction must work one-handed on ordinary phone sizes.

The dictation overlay should therefore:

- be reachable with the thumb if it requires tapping;
- avoid tiny stop/cancel targets;
- keep primary action near lower reachable space;
- not require top-of-screen interaction during active dictation.

If the overlay is centered above the keyboard, controls should remain comfortably tappable.

Avoid tiny icon-only controls with no hit padding.

---

# 173. Left-handed and right-handed considerations

Do not hard-code assumptions that the user interacts from the right side.

If the overlay has asymmetric controls, either:

- center the primary stop control; or
- allow configurable/flexible placement; or
- use a layout that is neutral to handedness.

For any persistent floating bubble/shortcut, let users reposition it.

---

# 174. Keyboard invocation surfaces

If technically supported, Vaani may also integrate with keyboard-adjacent entry points such as:

- a custom IME action;
- an accessibility shortcut while typing;
- a persistent floating button;
- a Quick Settings tile.

If a custom keyboard/IME integration exists, the UX should still preserve the same principles:

- fast start;
- compact listening state;
- minimal occlusion;
- safe insertion;
- no surprise sending.

Do not force users to replace their preferred keyboard unless that is the explicit product strategy.

---

# 175. Suggestion row and text alternatives

A useful advanced usability feature is a lightweight correction strip after dictation finishes, especially for uncertain critical terms.

Example:

```text
Did you mean:
Hyprland   hyper land   Hyperland
```

But this should be rare and contextual.

If shown, it should appear in a keyboard-adjacent location and be easy to dismiss.

Do not turn every dictation into a proofreading workflow.

By default, uncertainty should be handled internally unless a user choice is genuinely needed.

---

# 176. Cursor and selection feedback

When possible, Vaani should behave intelligently with selected text.

Use cases:

- replace selected phrase with dictated text;
- append at end of field;
- insert in middle of sentence.

The UI does not need to announce every cursor position, but it should behave consistently.

If selection replacement mode is active and it matters, a subtle hint can be shown:

```text
Replacing selected text
```

only if this improves clarity.

Do not overwhelm the overlay with editing-state trivia.

---

# 177. Usability feature set the keyboard experience should support

The UI/UX agent should account for these usability features if backend capability exists or is planned:

## Required / highly recommended

- clear start/stop state;
- cancel without insertion;
- insertion failure recovery;
- compact partial transcript;
- live readiness indication;
- one-handed reach;
- keyboard-safe placement;
- text-preserving fallback copy action;
- accessible touch targets;
- no accidental send;
- no full-screen takeover by default.

## Strong optional features

- keep keyboard visible;
- replace selected text intelligently;
- post-dictation alternative suggestions for critical low-confidence words;
- simple undo after insertion if technically feasible;
- haptic start/stop cues;
- remembered floating bubble location.

## Advanced / future features

- keyboard-specific integration mode;
- inline correction chip row;
- per-app dictation behavior;
- auto-spacing smarter rules;
- append vs replace modes;
- custom keyboard shortcut invocation.

Do not block V1 on advanced features.

---

# 178. Undo and retry after insertion

Usability improves significantly if the user can quickly undo a just-inserted dictation.

If technically feasible, support a short-lived action such as:

```text
Inserted
[ Undo ]
```

or a contextual retry/copy route.

This is particularly valuable when:

- punctuation is wrong;
- insertion happened in the wrong place;
- the user dictated the wrong phrase;
- a snippet expanded unexpectedly.

However, do not fake undo unless insertion tracking actually supports it.

If true undo is not possible, offer:

```text
Copy last dictation
```

or open History if enabled.

---

# 179. Accessibility for keyboard-adjacent dictation

Screen-reader users or motor-impaired users need predictable behavior.

Requirements:

- the start/stop/cancel targets must have clear accessibility labels;
- focus changes during overlay appearance must be controlled and non-chaotic;
- the overlay must not steal focus unnecessarily from the active field;
- TalkBack announcements should cover state changes, not every partial token;
- controls must be reachable and not too small;
- error recovery actions such as Copy / Try again / Open settings must be clear.

Do not assume visual proximity to keyboard is enough explanation.

Semantics matter.

---

# 180. Landscape + small device keyboard behavior

Landscape keyboards consume significant height.

Therefore:

- the overlay must shrink further in landscape;
- avoid multi-line transcript previews by default;
- use concise status;
- prioritize stop/cancel and clarity.

On small screens, the listening pill may reduce to:

```text
● Listening   ■
```

with optional progressive expansion only if needed.

Do not insist on showing every nice-to-have detail.

---

# 181. Keyboard-related anti-patterns

Explicitly avoid these UX mistakes:

```text
hiding the keyboard without warning
opening a full-screen recorder unnecessarily
covering the send key
covering the space bar
large blocking transcript cards over the keyboard
inserting text and auto-sending
requiring two hands for stop/cancel
making cancel tiny
showing unstable transcript flicker on every token
forgetting the dictated text after insertion failure
stealing focus from the active text field
```

If the UI does any of these, it is wrong.

---

# 182. Final instruction for the UI/UX agent

The UI/UX agent must integrate these new concerns into the main Vaani design system, not treat them as decorative extras.

Specifically:

- brand images must support Vaani's warm, calm, precise identity;
- the uploaded image should be treated as mood/reference material;
- keyboard-aware dictation behavior must be designed as a first-class interaction;
- usability must prioritize insertion safety, compactness, and one-handed use;
- no visual solution is acceptable if it harms typing flow.

When conflicts happen:

```text
typing flow > decorative overlay complexity
real product truth > fake premium polish
preservation and recoverability > automation flair
```

These rules are mandatory.
