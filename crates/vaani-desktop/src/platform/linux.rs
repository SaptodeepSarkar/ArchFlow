//! Linux desktop adapters. The Wayland path uses compositor-owned focus data,
//! wl-copy, and wtype's virtual-keyboard shortcut path. No transcript is put
//! in a shell command or key-dispatch argument.

use crate::DirectInserter;
use std::io::Write;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};
use vaani_core::engine::{EngineError, EngineErrorKind, InsertOutcome};

#[derive(Debug, Clone, Default, serde::Deserialize)]
struct ActiveWindow {
    #[serde(default)]
    address: String,
    #[serde(default)]
    class: String,
    #[serde(default)]
    focused: bool,
}

fn active_window() -> Result<ActiveWindow, EngineError> {
    let output = Command::new("hyprctl")
        .args(["activewindow", "-j"])
        .output()
        .map_err(|e| {
            EngineError::new(
                EngineErrorKind::Unavailable,
                format!("hyprctl unavailable: {e}"),
            )
        })?;
    if !output.status.success() {
        return Err(EngineError::new(
            EngineErrorKind::Unavailable,
            "focused window unavailable",
        ));
    }
    serde_json::from_slice(&output.stdout).map_err(|e| {
        EngineError::new(
            EngineErrorKind::Runtime,
            format!("focused window response invalid: {e}"),
        )
    })
}

fn is_terminal(class: &str) -> bool {
    let class = class.to_lowercase();
    [
        "foot",
        "kitty",
        "alacritty",
        "wezterm",
        "gnome-terminal",
        "konsole",
        "xterm",
        "ghostty",
    ]
    .iter()
    .any(|name| class.contains(name))
}

fn copy_wayland(text: &str, primary: bool) -> Result<(), EngineError> {
    if text.is_empty() {
        return Err(EngineError::new(
            EngineErrorKind::InvalidInput,
            "empty text",
        ));
    }
    let mut command = Command::new("wl-copy");
    command.args(["--sensitive", "--trim-newline"]);
    if primary {
        command.arg("--primary");
    }
    let mut child = command
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| {
            EngineError::new(
                EngineErrorKind::Unavailable,
                format!("wl-copy unavailable: {e}"),
            )
        })?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(text.as_bytes()).map_err(|e| {
            EngineError::new(
                EngineErrorKind::Runtime,
                format!("clipboard write failed: {e}"),
            )
        })?;
    }
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        match child.try_wait() {
            Ok(Some(status)) if status.success() => return Ok(()),
            Ok(Some(_)) => {
                return Err(EngineError::new(EngineErrorKind::Runtime, "wl-copy failed"))
            }
            Ok(None) if Instant::now() >= deadline => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(EngineError::new(
                    EngineErrorKind::Timeout,
                    "clipboard offer timed out",
                ));
            }
            Ok(None) => std::thread::sleep(Duration::from_millis(10)),
            Err(e) => {
                return Err(EngineError::new(
                    EngineErrorKind::Runtime,
                    format!("clipboard process wait failed: {e}"),
                ))
            }
        }
    }
}

/// Wayland clipboard adapter. `--foreground` is intentionally not used:
/// wl-copy's normal parent is reaped while its clipboard offer remains alive.
pub struct WlClipboard;

impl crate::ClipboardPort for WlClipboard {
    fn copy(&self, text: &str) -> Result<(), EngineError> {
        copy_wayland(text, false)
    }
}

/// Hyprland GUI insertion through clipboard plus a virtual Ctrl+V shortcut.
/// Terminals and shell-like multiline text remain copy-only by policy.
pub struct HyprlandInserter;

impl DirectInserter for HyprlandInserter {
    fn insert(&self, text: &str) -> Result<InsertOutcome, EngineError> {
        let window = active_window()?;
        if window.address.is_empty() || !window.focused {
            return Ok(InsertOutcome::Unavailable {
                reason: "focused editor unavailable".into(),
            });
        }
        if is_terminal(&window.class) {
            return Ok(InsertOutcome::Copied {
                reason: "terminal target is copy-only".into(),
            });
        }
        if text.contains('\n') && looks_shell_like(text) {
            return Ok(InsertOutcome::Copied {
                reason: "multiline shell-like text is copy-only".into(),
            });
        }
        copy_wayland(text, false)?;
        let status = Command::new("wtype")
            .args(["-M", "ctrl", "-k", "v", "-m", "ctrl"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|e| {
                EngineError::new(
                    EngineErrorKind::Unavailable,
                    format!("wtype unavailable: {e}"),
                )
            })?;
        if status.success() {
            Ok(InsertOutcome::Copied {
                reason: "paste requested through focused Wayland editor".into(),
            })
        } else {
            Ok(InsertOutcome::Unavailable {
                reason: "Wayland paste shortcut failed".into(),
            })
        }
    }
}

/// X11 clipboard adapter. `xclip` owns the selection after stdin is closed;
/// this is the same short-lived handoff pattern used by the Wayland clipboard
/// helper and keeps dictated text out of arguments and logs.
pub struct X11Clipboard;

impl crate::ClipboardPort for X11Clipboard {
    fn copy(&self, text: &str) -> Result<(), EngineError> {
        copy_x11(text)
    }
}

/// X11 insertion through `xdotool`'s paste shortcut. Terminals and shell-like
/// multiline text remain copy-only by policy.
pub struct X11Inserter;

impl DirectInserter for X11Inserter {
    fn insert(&self, text: &str) -> Result<InsertOutcome, EngineError> {
        if text.is_empty() {
            return Err(EngineError::new(
                EngineErrorKind::InvalidInput,
                "empty text",
            ));
        }
        let class = x11_active_window_class()?;
        if is_terminal(&class) || (text.contains('\n') && looks_shell_like(text)) {
            copy_x11(text)?;
            return Ok(InsertOutcome::Copied {
                reason: "terminal or shell-like target is copy-only".into(),
            });
        }
        copy_x11(text)?;
        let status = Command::new("xdotool")
            .args(["key", "--clearmodifiers", "ctrl+v"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map_err(|e| {
                EngineError::new(
                    EngineErrorKind::Unavailable,
                    format!("xdotool unavailable: {e}"),
                )
            })?;
        if status.success() {
            Ok(InsertOutcome::Copied {
                reason: "paste requested through focused X11 editor".into(),
            })
        } else {
            Ok(InsertOutcome::Unavailable {
                reason: "X11 paste shortcut failed".into(),
            })
        }
    }
}

fn copy_x11(text: &str) -> Result<(), EngineError> {
    if text.is_empty() {
        return Err(EngineError::new(
            EngineErrorKind::InvalidInput,
            "empty text",
        ));
    }
    let mut child = Command::new("xclip")
        .args(["-selection", "clipboard", "-in"])
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| {
            EngineError::new(
                EngineErrorKind::Unavailable,
                format!("xclip unavailable: {e}"),
            )
        })?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(text.as_bytes()).map_err(|e| {
            EngineError::new(
                EngineErrorKind::Runtime,
                format!("clipboard write failed: {e}"),
            )
        })?;
    }
    // X11 requires a selection owner to remain available after the write. A
    // successful xclip process is therefore intentionally handed off; an
    // immediate failure is still surfaced to the caller.
    std::thread::sleep(Duration::from_millis(10));
    match child.try_wait() {
        Ok(Some(status)) if !status.success() => {
            Err(EngineError::new(EngineErrorKind::Runtime, "xclip failed"))
        }
        Ok(_) => {
            std::mem::forget(child);
            Ok(())
        }
        Err(e) => Err(EngineError::new(
            EngineErrorKind::Runtime,
            format!("clipboard process wait failed: {e}"),
        )),
    }
}

fn x11_active_window_class() -> Result<String, EngineError> {
    let output = Command::new("xdotool")
        .args(["getactivewindow", "getwindowclassname"])
        .output()
        .map_err(|e| {
            EngineError::new(
                EngineErrorKind::Unavailable,
                format!("xdotool unavailable: {e}"),
            )
        })?;
    if !output.status.success() {
        return Err(EngineError::new(
            EngineErrorKind::Unavailable,
            "focused X11 window unavailable",
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_owned())
}

fn looks_shell_like(text: &str) -> bool {
    text.lines().any(|line| {
        let line = line.trim_start();
        line.starts_with("rm ")
            || line.starts_with("sudo ")
            || line.starts_with("git ")
            || line.starts_with("cargo ")
            || line.starts_with("make ")
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn x11_terminal_and_shell_guards_match_wayland_policy() {
        assert!(is_terminal("gnome-terminal"));
        assert!(is_terminal("XTerm"));
        assert!(!is_terminal("code"));
        assert!(looks_shell_like("git status\nmake test"));
        assert!(!looks_shell_like("write a meeting note\nfor review"));
    }
}
