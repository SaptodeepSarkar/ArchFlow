# Portable desktop controller

`crates/vaani-desktop` owns the platform-independent desktop lifecycle:

`Hidden → Listening → Finishing → Delivering → Hidden`

The overlay, global shortcut, focus, insertion, and clipboard implementations
are adapters. They are not allowed to alter the delivery policy:

1. Attempt safe direct insertion against the currently focused editor.
2. If the editor or platform rejects insertion, copy the complete text.
3. Report `Unavailable` only after the clipboard fallback also fails.

`DesktopRuntime` is the composition boundary used by a shell: it accepts
in-memory audio chunks, forwards partials to the overlay, finalizes the STT
session, runs the replaceable formatter plus deterministic personalization
pipeline, and delivers through the insertion/clipboard policy. Platform shells
remain responsible for capture, shortcuts, and rendering.

The controller is event-driven. Platform event loops call `invoke`, `preview`,
`finishing`, and `deliver`; it does not poll windows or spawn per-tick helper
commands. No transcript is logged or placed in command arguments by the
portable layer.

The crate now contains target-specific adapter foundations and a desktop-local
personalization repository: Linux uses
Hyprland focus metadata plus `wl-copy`/`wtype` for GUI paste with terminal and
shell-like copy-only safeguards; Windows uses the User32 `RegisterHotKey`
message loop. `PersonalizationRepository` stores vocabulary, snippets, and
replacements in the shared JSONL schema and applies the same deterministic
canonicalization/rendering rules. Windows accessibility, tray, clipboard, and
editor insertion are now represented by a User32 clipboard-plus-paste adapter;
the complete Windows shell/tray and focused-editor integration still need to
be connected.

`FirebaseRestProvider` can push and pull those records through Firestore using
an injected ID-token provider; it never owns credentials or participates in the
dictation path. Linux and Windows shells still need their platform-secure auth
binding and settings UX wired in.

`DesktopSyncClient` is the lifecycle bridge for a shell: it owns the local
repository, accepts optional email/password sign-in through `FirebaseEmailAuth`,
and runs one bounded sync cycle only when a session exists. Local rendering and
dictation do not depend on this client being signed in.

`SecureSessionStore` stores the refreshable session in the platform credential
store through keyring (Secret Service on Linux, Windows Credential Manager on
Windows). The shared crate never writes refresh tokens to config, JSONL, or
logs; a shell must explicitly opt into saving and restoring a session.

The `vaani-desktop` binary is a minimal cross-platform integration entry point:
`login` reads credentials interactively, `sync` restores the keyring session and
runs one bounded cycle, `status` reports local counts only, `personalize` opens
an interactive local control surface for vocabulary, snippets, and replacements,
and `sign-out` clears the keyring. Personalization values are read from stdin,
never command-line arguments, and are available without an account. It reads `VAANI_FIREBASE_PROJECT` and
`VAANI_FIREBASE_API_KEY` from the environment; passwords and tokens are never
command-line arguments.
