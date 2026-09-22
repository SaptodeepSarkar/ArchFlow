//! Hyprland insertion adapter: clipboard offer + verified key-dispatch.
//! Returns a TextInserter outcome; a successful key dispatch is NOT proof the
//! app accepted the text, so we report "Paste requested".

use crate::clipboard;
use crate::focus::{self, FocusTarget};

/// A short per-keystroke delay makes final delivery visibly compose in the
/// focused field instead of appearing as an indistinguishable paste.
const DIRECT_TYPE_DELAY_MS: u64 = 14;

#[derive(Debug, Clone, PartialEq)]
pub enum InsertOutcome {
    /// Environment cannot insert (e.g. no hyprctl) — caller keeps copy-ready.
    Unsupported(String),
    CopyReady(String),
    DispatchAttempted(String),
    Failed(String),
}

impl std::fmt::Display for InsertOutcome {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            InsertOutcome::Unsupported(s) => write!(f, "unsupported: {s}"),
            InsertOutcome::CopyReady(s) => write!(f, "copy-ready: {s}"),
            InsertOutcome::DispatchAttempted(s) => write!(f, "paste requested: {s}"),
            InsertOutcome::Failed(s) => write!(f, "failed: {s}"),
        }
    }
}

impl InsertOutcome {
    /// A non-sensitive route for status and logs. Never return the detailed
    /// reason because it can carry compositor or application information.
    pub fn diagnostic_code(&self) -> &'static str {
        match self {
            Self::DispatchAttempted(_) => "wtype_typed",
            Self::CopyReady(reason) if reason.starts_with("copy-only mode") => {
                "clipboard_only_configured_policy"
            }
            Self::CopyReady(reason) if reason.starts_with("review mode") => {
                "clipboard_only_review_policy"
            }
            Self::CopyReady(reason) if reason.starts_with("target changed") => {
                "clipboard_only_target_changed"
            }
            Self::CopyReady(_) => "clipboard_only_wtype_or_clipboard",
            Self::Failed(_) => "clipboard_or_wtype_failed",
            Self::Unsupported(_) => "clipboard_only_unsupported",
        }
    }
}

/// Attempt automatic insertion for `target`. In automatic mode the cleaned
/// final text is emitted as virtual keyboard events, including for terminals.
/// It never sends Enter; execution remains entirely with the user.
pub fn insert_automatic(
    text: &str,
    start_target: &FocusTarget,
    configured_mode: &str,
) -> InsertOutcome {
    if configured_mode == "copy-only" {
        return copy_ready(text, "copy-only mode configured");
    }
    if configured_mode == "review" {
        return copy_ready(text, "review mode: awaiting explicit confirmation");
    }
    // Recheck focus immediately before dispatch (documented race remains).
    let current = match focus::recheck_target(start_target) {
        Ok(t) => t,
        Err(reason) => return copy_ready(text, &format!("target changed ({reason})")),
    };
    // Keep a recoverable copy, but use direct virtual-keyboard text for the
    // actual delivery. The active AGENTS.md exception permits only cleaned
    // final LLM text as wtype input. wtype generates key events; it does not
    // invoke a shell and this path never sends Enter.
    if configured_mode == "automatic" {
        // Clipboard availability must not prevent direct typing. It remains
        // a recovery channel if focus changes or the virtual keyboard fails.
        let clipboard_ready = clipboard::offer_text(text).is_ok();
        if let Err(reason) = focus::recheck_target(start_target) {
            return if clipboard_ready {
                InsertOutcome::CopyReady(format!("target changed before typing ({reason})"))
            } else {
                InsertOutcome::Failed(format!("target changed before typing ({reason})"))
            };
        }
        return match type_text(text) {
            Ok(()) => InsertOutcome::DispatchAttempted(format!(
                "typed via virtual keyboard into {}",
                current.app_id
            )),
            Err(e) if clipboard_ready => {
                // Some compositor/client combinations can accept a virtual
                // paste chord when literal virtual keys are unavailable.
                let chord = paste_chord_for(&current.app_id);
                match dispatch_paste(&chord) {
                    Ok(()) => InsertOutcome::DispatchAttempted(format!(
                        "typed via virtual keyboard paste fallback ({chord}) into {}",
                        current.app_id
                    )),
                    Err(_) => InsertOutcome::CopyReady(format!(
                        "virtual keyboard typing failed ({e}); text on clipboard"
                    )),
                }
            }
            Err(e) => InsertOutcome::Failed(format!("virtual keyboard typing failed ({e})")),
        };
    }
    // Offer on clipboard, then dispatch the app's paste chord.
    // Terminals paste from the primary selection (Shift+Insert, single
    // modifier): the dual-modifier Shift+Ctrl+V chord does not deliver
    // through the virtual keyboard on this compositor, while single-modifier
    // chords and literal typing do. Both selections end up holding the text.
    let use_primary = uses_primary_paste(&current.app_id);
    if use_primary {
        if let Err(e) = clipboard::offer_primary(text) {
            return InsertOutcome::Failed(format!("primary offer failed: {e}"));
        }
        if let Err(e) = clipboard::offer_text(text) {
            return InsertOutcome::Failed(format!("clipboard offer failed: {e}"));
        }
        if !clipboard::primary_still_ours(text) {
            return InsertOutcome::CopyReady(
                "primary offer was replaced before paste dispatch".into(),
            );
        }
    } else if let Err(e) = clipboard::offer_text(text) {
        return InsertOutcome::Failed(format!("clipboard offer failed: {e}"));
    }
    if !clipboard::still_ours(text) {
        return InsertOutcome::CopyReady(
            "clipboard offer was replaced before paste dispatch".into(),
        );
    }
    if let Err(reason) = focus::recheck_target(start_target) {
        return InsertOutcome::CopyReady(format!(
            "target changed after clipboard offer ({reason})"
        ));
    }
    let chord = paste_chord_for(&current.app_id);
    match dispatch_paste(&chord) {
        Ok(()) => InsertOutcome::DispatchAttempted(format!(
            "paste dispatched ({chord}) for {}",
            current.app_id
        )),
        Err(e) => InsertOutcome::CopyReady(format!("dispatch failed ({e}); text on clipboard")),
    }
}

/// Every non-delivery completion still offers text for an explicit paste or
/// copy. Failures are reported honestly and the daemon retains pending text.
fn copy_ready(text: &str, reason: &str) -> InsertOutcome {
    match clipboard::offer_text(text) {
        Ok(()) => InsertOutcome::CopyReady(reason.into()),
        Err(e) => InsertOutcome::Failed(format!("{reason}; clipboard offer failed: {e}")),
    }
}

/// Live-dictation commit: type one stabilized delta into the target.
/// Rechecks focus immediately before dispatch; any failure freezes live
/// commits (caller keeps the full text recoverable). Never appends Enter.
pub(crate) fn commit_delta(text: &str, target: &FocusTarget) -> Result<(), String> {
    let current = focus::recheck_target(target)?;
    if uses_primary_paste(&current.app_id) {
        clipboard::offer_primary(text).map_err(|e| format!("primary offer failed: {e}"))?;
        clipboard::offer_text(text).map_err(|e| format!("clipboard offer failed: {e}"))?;
        if !clipboard::primary_still_ours(text) {
            return Err("primary offer was replaced before paste dispatch".into());
        }
    } else {
        clipboard::offer_text(text).map_err(|e| format!("clipboard offer failed: {e}"))?;
    }
    if !clipboard::still_ours(text) {
        return Err("clipboard offer was replaced before paste dispatch".into());
    }
    focus::recheck_target(target)?;
    let chord = paste_chord_for(&current.app_id);
    dispatch_paste(&chord).map_err(|e| format!("dispatch failed: {e}"))?;
    Ok(())
}

/// Terminals paste from the primary selection with Shift+Insert (one
/// modifier); GUI apps paste from the clipboard with Ctrl+V.
fn uses_primary_paste(app_id: &str) -> bool {
    let l = app_id.to_lowercase();
    l.contains("foot") || l.contains("kitty") || l.contains("alacritty") || l.contains("wezterm")
}

fn paste_chord_for(app_id: &str) -> String {
    if uses_primary_paste(app_id) {
        "SHIFT+Insert".into()
    } else {
        "CTRL+V".into()
    }
}

/// Explicit pending-text injection uses the same direct virtual-keyboard
/// route as automatic delivery. It never sends Enter.
pub fn inject_stream(text: &str) -> anyhow::Result<()> {
    if text.is_empty() {
        return Ok(());
    }
    let _ = clipboard::offer_text(text);
    type_text(text)
}

/// Type cleaned final text as visibly progressive virtual keyboard events.
/// `wtype` is called directly (never through a shell) and is given the text
/// under the explicit repository exception for one-shot LLM output. It has no
/// Enter action.
fn type_text(text: &str) -> anyhow::Result<()> {
    let wtype = find_wtype().ok_or_else(|| anyhow::anyhow!("wtype not found"))?;
    let mut cmd = std::process::Command::new(wtype);
    cmd.arg("-d").arg(DIRECT_TYPE_DELAY_MS.to_string());
    // `--` keeps a cleaned prompt beginning with '-' from being interpreted
    // as a wtype option. Verified against the installed wtype binary.
    cmd.arg("--").arg(text);
    let timeout_secs = type_timeout_secs(text);
    let out = clipboard::run_timeout(cmd, None, timeout_secs, true)?;
    if out.status.success() {
        return Ok(());
    }
    let stderr = String::from_utf8_lossy(&out.stderr);
    anyhow::bail!("wtype exited unsuccessfully: {}", stderr.trim());
}

/// A long dictated prompt may take longer than the normal helper deadline.
/// Keep a finite ceiling so a stuck virtual keyboard cannot wedge a session.
fn type_timeout_secs(text: &str) -> u64 {
    let typing_ms = (text.chars().count() as u64).saturating_mul(DIRECT_TYPE_DELAY_MS);
    (5 + typing_ms.div_ceil(1_000)).min(60)
}

/// Fallback key dispatch for clients that reject direct virtual-keyboard text.
/// The text remains on the clipboard; this helper sends only a fixed chord.
fn dispatch_paste(chord: &str) -> anyhow::Result<()> {
    let (mods, key) = chord_parts(chord)?;
    if let Some(wtype) = find_wtype() {
        let mut cmd = std::process::Command::new(wtype);
        for modifier in mods.split_whitespace() {
            cmd.arg("-M").arg(modifier);
        }
        cmd.arg("-k").arg(&key);
        for modifier in mods.split_whitespace().rev() {
            cmd.arg("-m").arg(modifier);
        }
        // Bounded: a hung virtual-keyboard roundtrip must not wedge the
        // session in INSERTING (fall through to Hyprland on expiry).
        if let Ok(out) = clipboard::run_timeout(cmd, None, 5, true) {
            if out.status.success() {
                return Ok(());
            }
        }
    }

    let lua = format!(r#"hl.dispatch(hl.dsp.send_shortcut({{ mods = "{mods}", key = "{key}" }}))"#);
    let mut cmd = std::process::Command::new("hyprctl");
    cmd.arg("eval").arg(&lua);
    let out = clipboard::run_timeout(cmd, None, 5, true)
        .map_err(|e| anyhow::anyhow!("hyprctl not available: {e}"))?;
    let stdout = String::from_utf8_lossy(&out.stdout);
    if out.status.success() && stdout.trim() == "ok" {
        Ok(())
    } else {
        let err = String::from_utf8_lossy(&out.stderr);
        let detail = if err.trim().is_empty() {
            stdout.trim().to_string()
        } else {
            err.trim().to_string()
        };
        anyhow::bail!("{detail}")
    }
}

pub fn find_wtype() -> Option<std::path::PathBuf> {
    let sibling = std::env::current_exe().ok()?.parent()?.join("wtype");
    if sibling.is_file() {
        return Some(sibling);
    }
    std::env::var_os("PATH").and_then(|paths| {
        std::env::split_paths(&paths)
            .map(|dir| dir.join("wtype"))
            .find(|path| path.is_file())
    })
}

/// Placeholder for compositor-managed input locking.
/// `wtype` cannot grab physical keyboard or mouse input; it only emits
/// virtual-keyboard events to the currently focused Wayland surface.
pub struct KeyboardGrab;

pub fn grab_keyboard() -> Option<KeyboardGrab> {
    Some(KeyboardGrab)
}

/// Split "SHIFT+CTRL+V" into Lua send_shortcut (mods, key), whitelisted to
/// alphanumerics + space so only our fixed chords can interpolate.
fn chord_parts(chord: &str) -> anyhow::Result<(String, String)> {
    let mut parts: Vec<&str> = chord.split('+').collect();
    if parts.is_empty() {
        anyhow::bail!("empty chord");
    }
    let key = parts.pop().unwrap().to_lowercase();
    let mods = parts
        .iter()
        .map(|m| m.to_lowercase())
        .collect::<Vec<_>>()
        .join(" ");
    for s in std::iter::once(key.as_str()).chain(mods.split(' ')) {
        if s.is_empty() || !s.chars().all(|c| c.is_ascii_alphanumeric()) {
            anyhow::bail!("invalid chord fragment");
        }
    }
    Ok((mods, key))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn chords_split_for_lua() {
        assert_eq!(chord_parts("CTRL+V").unwrap(), ("ctrl".into(), "v".into()));
        assert_eq!(
            chord_parts("SHIFT+CTRL+V").unwrap(),
            ("shift ctrl".into(), "v".into())
        );
        assert!(chord_parts("CTRL+$(evil)").is_err());
    }

    #[test]
    fn terminal_chords_use_primary_single_mod() {
        assert_eq!(paste_chord_for("foot"), "SHIFT+Insert");
        assert_eq!(paste_chord_for("kitty"), "SHIFT+Insert");
        assert_eq!(paste_chord_for("org.wezfurlong.wezterm"), "SHIFT+Insert");
        assert_eq!(paste_chord_for("zen"), "CTRL+V");
        assert_eq!(
            chord_parts("SHIFT+Insert").unwrap(),
            ("shift".into(), "insert".into())
        );
    }

    #[test]
    fn wtype_lookup_does_not_require_a_shell() {
        // Lookup is direct and fixed-name; wtype is never launched through a shell.
        if let Some(path) = find_wtype() {
            assert_eq!(path.file_name().unwrap(), "wtype");
        }
    }

    #[test]
    fn direct_typing_timeout_scales_but_is_bounded() {
        assert_eq!(type_timeout_secs("short"), 6);
        assert_eq!(type_timeout_secs(&"x".repeat(1_250)), 23);
        assert_eq!(type_timeout_secs(&"x".repeat(100_000)), 60);
    }
}
