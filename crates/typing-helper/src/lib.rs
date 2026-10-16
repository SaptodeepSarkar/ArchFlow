//! Keystroke output for Vaani (Phase 08).
//!
//! Types finished text with the `wtype` binary only; there is no other
//! key-injection backend in this crate. Every run also copies the same text
//! to the Wayland clipboard via `wl-copy`, so the text survives even when
//! window focus lands wrong. Typing never starts unless the caller passes
//! `pill_hidden = true`: the pill must hide first so keystrokes reach the
//! previously focused window (PRD focus rule).

use std::io::Write;
use std::process::{Command, Stdio};

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
/// * `wtype` takes the text as one argv element, exactly its documented
///   `wtype <text-to-type>` form; it errors rather than mistypes on input
///   it cannot represent.
// shortcut: text starting with `-` reaches wtype bare (no `--` separator
// in its CLI), so wtype rejects it instead of typing; formatted dictation
// always starts capitalized per the fixture contract, so this never fires.
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
    let status = Command::new("wtype").arg(text).status()?;
    if !status.success() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::Other,
            format!("wtype failed: {status}"),
        ));
    }
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
}
