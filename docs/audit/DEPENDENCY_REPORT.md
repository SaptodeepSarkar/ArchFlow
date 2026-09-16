# Dependency report

Date: 2026-09-16

## Rust workspace

The workspace contains four crates: `vaani-core`, `vaanid`, `vaani-cli`, and `vaani-worker`. The direct shared dependencies are Tokio, Serde/Serde JSON, TOML, Clap, Anyhow, Thiserror, Tracing/Tracing Subscriber, and UUID.

The dependency tree keeps the Linux economy-first design: the shared workspace has no heavyweight database, arbitrary plugin loader, or inference runtime. The portable desktop crate adds bounded HTTP and credential-store dependencies for optional Firebase sync/auth, while Android uses its existing SQLite/WorkManager/Firebase bridge without coupling those details into `vaani-core`.

## Android

The Android app uses platform UI and `SpeechRecognizer`, with AndroidX core, WorkManager, Firebase Auth/Firestore, and instrumentation dependencies for the implemented local-first personalization and optional sync paths. It deliberately does not use Compose or Room; the bounded SQLite repository remains behind the app-local store boundary.

## Decisions

- Do not add a large cross-platform UI framework to the Android IME.
- Add persistence dependencies only with a measured schema/migration need; keep the domain interfaces independent of the database.
- Add sync/auth SDKs only after local repositories and privacy boundaries exist.
- Keep inference runtimes behind adapters rather than adding them to UI modules.

## Cleanup status

No dependency is removed in this audit because unused-dependency proof is not available from `cargo tree` alone and Android build validation is blocked by the environment cache.
