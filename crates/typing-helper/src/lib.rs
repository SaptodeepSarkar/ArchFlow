//! Keystroke output for Vaani (Phase 08).
//!
//! Types finished text with the `wtype` binary only; there is no other
//! key-injection backend in this crate. Every run also copies the same text
//! to the Wayland clipboard via `wl-copy`, so the text survives even when
//! window focus lands wrong. Typing never starts unless the caller passes
//! `pill_hidden = true`: the pill must hide first so keystrokes reach the
//! previously focused window (PRD focus rule).

use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};

/// Gap between keystrokes in ms, so the line streams in letter by letter
/// instead of landing as one burst. Measured here: `wtype` spends ~5 ms of its
/// own per-key round trip on top, so 6 ms lands at ~11 ms/char (~4 s for 400).
const KEY_DELAY_MS: &str = "6";

/// System cue sounds, in preference order; the first one that exists plays.
const DONE_SOUNDS: [&str; 2] = [
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
];

/// Outcome of [`type_text`].
pub struct TypeReport {
    /// True when `wl-copy` accepted the text; false when no `wl-copy`
    /// binary was found and typing proceeded without a clipboard copy.
    pub clipboard_copied: bool,
}

/// Type `text` into the currently focused window.
///
/// * `pill_hidden` must be true — the caller confirms the pill already hid.
///   A false value fails without touching keyboard or clipboard.
/// * Clipboard first (`wl-copy` on stdin), keystrokes second (`wtype` argv).
/// * A clipboard failure never blocks typing: typing is the actual delivery,
///   so it proceeds and the report says the copy did not happen (otherwise
///   a clipboard-only failure would silently lose the text).
/// * `wtype -d <ms> -- <text>`: the delay makes the text appear key by key,
///   and `--` keeps a leading `-` from being read as a wtype flag.
pub fn type_text(text: &str, pill_hidden: bool) -> std::io::Result<TypeReport> {
    if !pill_hidden {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "pill still visible: refusing to type (focus rule)",
        ));
    }
    let clipboard_copied = match copy_to_clipboard(text) {
        Ok(v) => v,
        Err(e) => {
            eprintln!("typing-helper: clipboard copy failed ({e}); typing anyway");
            false
        }
    };
    let status = Command::new("wtype")
        .args(["-d", KEY_DELAY_MS, "--", text])
        .status()?;
    if !status.success() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::Other,
            format!("wtype failed: {status}"),
        ));
    }
    play_done_sound();
    Ok(TypeReport { clipboard_copied })
}

/// Pipe `text` into `wl-copy`. Returns false (with a stderr note) when no
/// `wl-copy` binary exists; any other failure is returned to the caller.
fn copy_to_clipboard(text: &str) -> std::io::Result<bool> {
    let mut child = match Command::new("wl-copy")
        .stdin(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
    {
        Ok(child) => child,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            eprintln!("typing-helper: wl-copy not found, typing without clipboard copy");
            return Ok(false);
        }
        Err(e) => return Err(e),
    };
    let mut stdin = child.stdin.take().expect("wl-copy stdin piped");
    stdin.write_all(text.as_bytes())?;
    drop(stdin);
    let status = child.wait()?;
    if !status.success() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::Other,
            format!("wl-copy failed: {status}"),
        ));
    }
    Ok(true)
}

/// First existing cue sound, in preference order; None when this machine has
/// no freedesktop sound theme.
fn pick_sound_file(exists: impl Fn(&str) -> bool) -> Option<&'static str> {
    DONE_SOUNDS.into_iter().find(|s| exists(s))
}

/// One short cue after the last keystroke: spawned and reaped on its own
/// thread, never awaited, never fatal, silent with no player or sound file.
/// Volume is kept low (~30%) so the done cue is subtle, not jarring.
/// pw-play uses a 0.0..=2.0 multiplier; paplay uses 0..=65536.
fn play_done_sound() {
    let Some(sound) = pick_sound_file(|p| Path::new(p).is_file()) else {
        return;
    };
    if let Ok(mut child) = Command::new("pw-play")
        .args(["--volume", "0.3", sound])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        std::thread::spawn(move || {
            let _ = child.wait();
        });
        return;
    }
    if let Ok(mut child) = Command::new("paplay")
        .args(["--volume", "20000", sound])
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
    {
        std::thread::spawn(move || {
            let _ = child.wait();
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn refuses_while_pill_visible() {
        // Needs no compositor: must fail before spawning anything.
        match type_text("Hello.", false) {
            Err(e) => assert_eq!(e.kind(), std::io::ErrorKind::InvalidInput),
            Ok(_) => panic!("typed while pill visible"),
        }
    }

    #[test]
    fn done_sound_falls_back_then_goes_silent() {
        let only = |want: &'static str| move |p: &str| p == want;
        assert_eq!(pick_sound_file(only(DONE_SOUNDS[0])), Some(DONE_SOUNDS[0]));
        assert_eq!(pick_sound_file(only(DONE_SOUNDS[1])), Some(DONE_SOUNDS[1]));
        assert_eq!(pick_sound_file(|_| false), None);
    }
}
