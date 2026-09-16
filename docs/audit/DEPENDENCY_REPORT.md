# Dependency report

Date: 2026-09-16

## Rust workspace

The workspace contains four crates: `vaani-core`, `vaanid`, `vaani-cli`, and `vaani-worker`. The direct shared dependencies are Tokio, Serde/Serde JSON, TOML, Clap, Anyhow, Thiserror, Tracing/Tracing Subscriber, and UUID.

The dependency tree contains no database, Firebase, HTTP client, arbitrary plugin loader, or heavyweight inference runtime. That is consistent with the current Linux economy-first design, but it also explains why personalization, sync, and cross-platform shells are not implemented.

## Android

The Android app directly declares only `androidx.core:core-ktx:1.15.0`; it uses platform UI and `SpeechRecognizer`. There is no Room/DataStore, Firebase Auth/Firestore, Compose, or instrumentation dependency today.

## Decisions

- Do not add a large cross-platform UI framework to the Android IME.
- Add persistence dependencies only with a measured schema/migration need; keep the domain interfaces independent of the database.
- Add sync/auth SDKs only after local repositories and privacy boundaries exist.
- Keep inference runtimes behind adapters rather than adding them to UI modules.

## Cleanup status

No dependency is removed in this audit because unused-dependency proof is not available from `cargo tree` alone and Android build validation is blocked by the environment cache.
