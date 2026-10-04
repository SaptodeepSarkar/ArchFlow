# Desktop and Super+H HUD polish

Desktop refinements keep the QML-derived hierarchy and light palette: compact
window controls, a single-line local badge, paired model/language fields,
segmented retention choices and current Home summaries after settings changes.
All five pages were rendered and inspected at 920×680 with a disposable example
config. Screenshots are the actual GTK widgets, not website mockups.

The HUD is now a compact horizontal, bottom-centered white/sky layer surface.
Its five bars use finite, clamped microphone amplitude events only while
recording. Captions reflect daemon state; no transcript is displayed or logged.
Finish, Cancel and Copy controls are visible only in appropriate states and
carry accessible names. Production still uses no keyboard focus and no
exclusive zone, with a 24-pixel bottom margin; unsupported compositors fail
closed instead of opening a focus-stealing normal window.

Behavior fixes:

- Consume the daemon's initial state snapshot, so an already-idle session can
  dismiss. Socket disconnect also exits the HUD.
- Reject stale amplitude/completion events. An old HUD exits when a different
  session starts. Overlay processes are non-unique to avoid reactivating a
  lingering surface for a new dictation.
- Bind HUD Stop/Cancel/Copy requests to their session. The daemon checks Stop
  and Cancel while holding the session lock, and validates Copy before reading
  pending text. Legacy sessionless clients remain supported.
- Give terminal notices 360 ms, clipboard confirmations 2.2 s and errors 1.6 s.
  The daemon allows bounded graceful exit and reaps/kills children within 3 s,
  including cancelled/replaced overlays. The installed sibling executable is
  preferred under systemd's minimal PATH.

Verification: 27 targeted Rust tests passed, one hardware test ignored. Added
regressions cover initial snapshots, stale session events, finite real amplitude,
clipboard-notice reset and stale daemon controls preserving current recording
and pending text. Native release builds and five-page Xvfb smoke passed.

`hud-recording.png`, `hud-cleaning.png` and `hud-ready.png` use the explicit
`--overlay-preview=STATE` visual-review mode: no daemon connection, no real
microphone, disabled buttons and no fabricated audio animation. Preview mode
alone permits an ordinary X11 window; production does not. Actual Super+H,
Wayland anchoring, compositor scaling, focus preservation, pointer controls and
microphone timing remain physical/session validation gates. No physical results
are inferred from screenshots or unit tests. No Android or website change is
included in this desktop/HUD phase.
