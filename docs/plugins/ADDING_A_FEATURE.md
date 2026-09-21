# Adding a feature

Features are portable domain behavior plus platform adapters. The feature must preserve text and remain usable in local-only mode.

## 1. Define the interface

Add a small contract to `vaani-core` with serializable input/output types and typed errors. Keep audio, transcripts, credentials, UI widgets, and OS calls out of the portable contract unless they are explicitly the feature’s boundary.

## 2. Register it

Add a trusted implementation to the platform composition root. Registration must be explicit and versioned; do not load arbitrary dynamic code. Configuration should identify capabilities and safe defaults.

## 3. Implement deterministic behavior first

Use rules for exact operations such as snippets and replacements. If a model is involved, constrain and validate its output against the source text before it can reach insertion.

## 4. Add persistence and privacy boundaries

Persist through the local repository abstraction. Define schema version, migration, deletion, and whether the record is eligible for optional sync. Never sync audio or raw dictation by implication.

## 5. Add platform hooks

Android owns IME lifecycle, permissions, accessibility, and touch UI. Linux and Windows own global invocation, overlay, tray, focus, and insertion. Every adapter needs a clipboard/recovery outcome when direct insertion is unavailable.

## 6. Expose the UI

Add the feature to the appropriate surface: Android Home/Personalize/Settings, Linux/Windows control center, or the transient overlay. Do not put long-lived settings into onboarding.

## 7. Test and benchmark

Add core contract tests, adapter tests, failure/recovery tests, migration tests, and privacy tests. If the feature affects inference or insertion, measure latency, CPU/RAM, and text-preservation behavior before and after.

## Release gate

The feature is not complete until local-only behavior works, failures preserve user text, platform fallbacks are explicit, and documentation explains permissions, configuration, tests, and benchmark implications.
