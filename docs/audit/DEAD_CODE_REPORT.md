# Dead-code and obsolete-artifact report

Date: 2026-09-16

This report is intentionally conservative. A compiler warning is a lead, not proof that code is safe to delete.

## Candidates requiring follow-up

| Candidate | Evidence | Action |
|---|---|---|
| nested `very_quiet_voice_level_is_not_discarded` test in `vaani-core/src/vad.rs` | Rust warns `cannot test inner items` and `dead_code` | Move into the existing test module, then retain as regression coverage |
| `vaanid::clipboard::clear_if_ours` | `dead_code` warning | Confirm cleanup lifecycle; remove only if replacement cleanup path covers it |
| `vaanid::capture::CaptureHandle::{device,started_at,drain}` | warnings | Determine whether diagnostics/metrics will consume them |
| `vaanid::inserter::{commit_delta,KeyboardGrab,grab_keyboard}` | warnings | Confirm abandoned insertion design versus future Windows/Linux adapter needs |
| `vaanid::daemon::copy_fallback`, `Shared::{ui_level,residency_warm_until}` | warnings | Trace current fallback/event behavior before removal |
| ignored training checkpoints/caches | `git status --ignored` shows local outputs only | Keep out of Git and active runtime; do not delete user-local experiments |

## Confirmed repository hygiene findings

- No model binaries or checkpoints are tracked by Git.
- Android `google-services.json` is untracked and must remain user-owned; it is not added by this work.
- Generated build/cache directories are ignored (`target/`, Android build/cache directories, model/training caches).
- No duplicate production Android source tree was found; Stitch HTML/PNG files are reference artifacts.

## Required deletion gate

Before deleting any candidate: locate all call sites, add or identify replacement tests, run `cargo test --workspace`, and document the reason in the change commit.
