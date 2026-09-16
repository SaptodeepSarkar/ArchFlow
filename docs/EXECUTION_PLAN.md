# Vaani ecosystem execution plan

Date: 2026-09-16

This plan preserves the mission scope while delivering vertical slices.

## Phase 0 — audit and decisions

Audit current code, models, dependencies, tests, environment, and product research. Record ADRs and preserve historical evidence. Status: baseline recorded in `docs/audit/`.

## Phase 1 — LEGO core

Add portable contracts for STT, formatting, context, personalization, deterministic rules, insertion outcomes, storage, sync, and metrics. Define serializable schemas and error types. No platform UI dependency. **Complete:** engine, personalization, model, sync, and JSONL local-storage contracts are present and tested.

## Phase 2 — local personalization

Implement vocabulary, snippets, replacements, ordering/boundary rules, migrations, and privacy-safe local persistence. Wire Android first and expose the same domain API to desktop. **In progress:** deterministic rules, bounded Android SQLite local store/UI with legacy preference migration, Linux JSONL import/render, and desktop local repository writes are wired; Android DataStore preference migration tests and desktop settings UI remain.

## Phase 3 — model registry and V5

Add manifest discovery/checksum/capability validation and benchmark registration. Route current Linux V5/cozy paths through it; retain CPU-first fallback and honest backend labels.

## Phase 4 — Android product completion

Refactor the IME around the explicit dictation state machine, preserve recoverable text on insertion failure, complete keyboard behavior, and connect onboarding/home/personalization/settings. Validate through ADB on a real emulator when the host permits it.

## Phase 5 — optional local-first sync

Add optional authentication, Firestore rules, background synchronization, tombstones, conflict resolution, migrations, and offline tests. **In progress:** portable sync records/coordinator, persisted outbox, Firestore rules/emulator tests, and Android email/password plus personalization provider are implemented; production Auth-provider enablement and Linux/Windows provider adapters remain. Never sync audio or raw dictations by default.

## Phase 6 — desktop ecosystem

Define a shared desktop domain layer, then implement Linux overlay/tray/insertion and a separate Windows shell/insertion adapter. Use clipboard recovery whenever direct insertion is unavailable. **In progress:** portable lifecycle/fallback logic, Linux Hyprland/Wayland adapters, and a Windows User32 global-hotkey foundation are implemented; full shells, tray, audio/STT wiring, and Windows insertion remain.

## Phase 7 — performance and release

Build reproducible CPU/latency/memory benchmarks, add CI for Rust/Android/Linux/Windows where practical, harden packaging, security, docs, and the Android/Linux/Windows cross-device scenario.

## Current blockers

Firebase project access is available, but Cloud Firestore is not enabled in the existing development project; no cloud resource or billing was created. Firebase emulator rules tests, ADB, and Android Gradle are verified locally; live authenticated cloud sync, live speech/insertion, and complete desktop shells remain unverified.
