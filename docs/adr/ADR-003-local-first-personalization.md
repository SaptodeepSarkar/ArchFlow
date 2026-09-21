# ADR-003 — Local-first personalization with optional sync

Date: 2026-09-16

## Problem

Vocabulary, snippets, replacements, and settings must work without an account or network, then synchronize across devices when the user opts in.

## Options considered

1. Cloud-first Firestore documents.
2. Per-platform local stores with no common schema.
3. A shared logical schema with local repositories and an optional background sync provider.

## Evidence

The current app has a bounded SQLite personalization store and an optional Android Firebase bridge; the Linux JSONL repository and shared sync coordinator are also present. Firestore supports offline persistence and synchronization semantics, but the product requirement forbids making dictation wait on the network. Wispr’s current product distinguishes local transcript history from selected synchronized personalization/notes, reinforcing a deliberate privacy boundary. [Firestore offline data](https://firebase.google.com/docs/firestore/manage-data/enable-offline), [Wispr Flow navigation](https://docs.wisprflow.ai/articles/5096240724-navigating-the-wispr-flow-app-desktop-ios-and-android)

## Decision

Define shared records with stable IDs, timestamps, version/schema fields, and tombstones. Local writes are authoritative for immediate behavior. A background sync provider is optional and initially syncs vocabulary, snippets, replacements, and explicitly portable preferences only. Audio and raw dictation history are excluded by default. Conflicts use deterministic whole-record last-write-wins per record using a device-persisted Lamport-style logical clock, writer-device ID, revision, and deletion tombstones; the implementation must expose conflict diagnostics. Wall-clock timestamps remain useful for display and retention, but do not decide convergence alone.

## Tradeoffs

The schema and tombstone lifecycle add complexity, but dictation remains available offline and privacy defaults are clear.

## Reversal cost

Low to moderate: a different cloud provider can implement the sync interface; changing conflict semantics after multi-device data exists is expensive, so the schema must version them from the start.
