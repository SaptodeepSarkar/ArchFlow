# ADR-005 — Android typed settings, structured local data, and injectable STT

Date: 2026-09-16

## Problem

The Android app currently reads untyped `SharedPreferences` keys directly from the Activity, IME, onboarding, and UI helper. The IME also constructs the concrete Android recognizer directly, making lifecycle and failure behavior difficult to test or replace with a Vaani-owned PCM engine.

## Options considered

1. Continue direct `SharedPreferences` and concrete recognizer construction.
2. Put all data in one database and all recognition in the IME service.
3. Use typed repositories, structured local storage for user data, and an injectable STT session factory.

## Evidence

The repository initially had no Android test sources or structured database. Android recommends DataStore for small settings and Room for structured data with migrations and partial updates. The current implementation uses a bounded platform SQLite repository for personalization to keep the IME dependency-light; DataStore migration for small settings remains. `SpeechRecognizer` requires main-thread interaction and lifecycle cleanup; on-device recognition availability is device/OEM dependent and is not equivalent to bundling a Vaani model. [DataStore](https://developer.android.com/topic/libraries/architecture/datastore), [Room](https://developer.android.com/training/data-storage/room), [SpeechRecognizer](https://developer.android.com/reference/android/speech/SpeechRecognizer), [InputMethodService](https://developer.android.com/reference/android/inputmethodservice/InputMethodService)

## Decision

Create typed `SettingsRepository` and `PersonalizationRepository` boundaries. Use Preferences DataStore for language, theme, cleanup, onboarding/readiness, and other small settings; use Room or the current compatible SQLite repository for vocabulary, snippets, replacements, and future opt-in history. Migrate existing `vaani` preference keys without deleting them until migration succeeds.

Define `SttSession`/factory semantics for start, stop, cancel, close, callbacks, and language support. Keep `AndroidOnDeviceSttSession` as one implementation and a future native PCM engine as another. Keep recognizer operations on the main thread and always destroy sessions after completion.

## Tradeoffs

This adds repository/migration code and Android dependencies, but makes the IME testable, preserves local-only operation, and prevents Android backend details from shaping the shared pipeline.

## Reversal cost

Moderate: changing the local database requires migrations, while the repository and STT interfaces make backend replacement relatively cheap.
