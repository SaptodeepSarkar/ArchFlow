# Portable desktop controller

`crates/vaani-desktop` owns the platform-independent desktop lifecycle:

`Hidden → Listening → Finishing → Delivering → Hidden`

The overlay, global shortcut, focus, insertion, and clipboard implementations
are adapters. They are not allowed to alter the delivery policy:

1. Attempt safe direct insertion against the currently focused editor.
2. If the editor or platform rejects insertion, copy the complete text.
3. Report `Unavailable` only after the clipboard fallback also fails.

`DesktopRuntime` is the composition boundary used by a shell. A shell can read
its current state and active session, and it accepts
in-memory audio chunks, forwards partials to the overlay, finalizes the STT
session, runs the replaceable formatter plus deterministic personalization
pipeline, and delivers through the insertion/clipboard policy. Platform shells
remain responsible for capture, shortcuts, and rendering.

`AudioFrontEnd` is the capture-side composition boundary. It accepts arbitrary
capture chunk sizes, runs the optional in-memory denoiser, buffers to the
bounded VAD block size, and returns every sample with an activity/level hint.
The hint is for UI and endpoint policy; it does not discard audio before STT.
Its `AudioChunk` output can be handed directly to
`DesktopRuntime::feed_audio_chunk`.
`DesktopRuntime` also enforces the shared 120-second per-session audio cap
before forwarding a chunk to STT.
`WorkerSttEngine` is the desktop process adapter for the existing
`vaani-worker` stdin-PCM protocol: it buffers only the bounded session audio,
writes PCM to the worker on finalization, and parses the final response in
memory. It deliberately does not pass audio, transcripts, or vocabulary in
arguments or control JSON.
Flushing the front-end resets VAD hangover and counters before the next
utterance, preventing prior speech from affecting a new session.
`DesktopSession` packages those two boundaries so a shell can start, push
arbitrary capture chunks, finish, or cancel without duplicating lifecycle
plumbing.
The session also exposes `speech_seen` so a shell can avoid finalizing a
silence-only utterance and thereby avoid phantom recognizer output.
`finish_if_speech` makes that policy atomic: silence cancels the STT session
and returns no delivery report, while speech follows the normal finalization
and insertion path.

`ShortcutSpec` is the shared validated invocation format. It accepts
case-insensitive `CTRL`, `ALT`, `SHIFT`, and `SUPER` modifiers plus a bounded
key set, canonicalizes ordering, and is translated to User32 virtual keys on
Windows. Linux shells can use the same canonical value when generating their
compositor binding.

The controller is event-driven. Platform event loops call `invoke`, `preview`,
`finishing`, and `deliver`; it does not poll windows or spawn per-tick helper
commands. No transcript is logged or placed in command arguments by the
portable layer.

The crate now contains target-specific adapter foundations and a desktop-local
personalization repository: Linux has explicit Hyprland/Wayland and X11
adapters. The Wayland path uses Hyprland focus metadata plus
`wl-copy`/`wtype`, while the X11 path uses optional `xclip`/`xdotool`; both
retain terminal and shell-like copy-only safeguards. Windows uses the User32
`RegisterHotKey` message loop. `PersonalizationRepository` stores vocabulary, snippets, and
replacements in the shared JSONL schema and applies the same deterministic
canonicalization/rendering rules. Windows accessibility, tray, clipboard, and
editor insertion are now represented by a User32 clipboard-plus-paste adapter;
when the paste dispatch is accepted, it reports “paste requested” while
retaining the complete clipboard text rather than claiming editor acceptance.
The Windows `run` entry point now composes the hotkey, capture, worker STT,
overlay, tray, and session loop; runtime hardware validation and a richer
settings surface remain release work.

The current verification host has `wl-copy` and `wtype`, but not `xclip` or
`xdotool`. X11 policy and adapter behavior are therefore contract-tested only;
no live X11 clipboard or focused-editor insertion result is claimed.

On Windows, `WindowsAudioCapture` uses the default WASAPI input device through
`cpal`, converts supported device formats to bounded mono `f32` blocks in
memory, and exposes those blocks to the same `AudioFrontEnd` contract. Device
selection, session timing, and delivery remain shell responsibilities; no
audio is serialized or passed through process arguments.
`WindowsSessionLoop` supplies the event-driven shell bridge: User32 hotkey and
audio notifications share one message loop, capture starts/stops with the
toggle, and completed sessions call `finish_if_speech` before delivery.
`WindowsOverlay` implements the shared overlay contract as a topmost tool
window, and `WindowsTray` registers a Shell_NotifyIcon callback on that same
window. They are presentation adapters only; they never transition the core
state machine or perform insertion themselves.

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
`doctor` reports platform and insertion prerequisites without touching clipboard
or dictation data, and `sign-out` clears the keyring. Personalization values are read from stdin,
never command-line arguments, and are available without an account. It reads `VAANI_FIREBASE_PROJECT` and
`VAANI_FIREBASE_API_KEY` from the environment; passwords and tokens are never
command-line arguments.
