# Portable desktop controller

`crates/vaani-desktop` owns the platform-independent desktop lifecycle:

`Hidden → Listening → Finishing → Delivering → Hidden`

The overlay, global shortcut, focus, insertion, and clipboard implementations
are adapters. They are not allowed to alter the delivery policy:

1. Attempt safe direct insertion against the currently focused editor.
2. If the editor or platform rejects insertion, copy the complete text.
3. Report `Unavailable` only after the clipboard fallback also fails.

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
