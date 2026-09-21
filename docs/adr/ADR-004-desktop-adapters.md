# ADR-004 — Explicit desktop adapters and safe insertion fallback

Date: 2026-09-16

## Problem

Linux Wayland/X11 and Windows expose different global-shortcut, focus, tray, accessibility, and text-insertion capabilities. A single synthetic-keyboard implementation would be unreliable and unsafe.

## Options considered

1. Reuse Hyprland commands everywhere.
2. Use one cross-platform synthetic input library as the insertion authority.
3. Define portable outcomes and implement explicit Linux Wayland/X11 and Windows adapters.

## Evidence

Wayland does not provide a universal application key-injection API; global shortcuts are exposed through desktop/compositor facilities. The X11 stack has separate passive grabs and XTest injection. Windows provides `RegisterHotKey`, UI Automation control patterns, and `SendInput`, but `SendInput` is constrained by User Interface Privilege Isolation. [XDG Global Shortcuts portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.GlobalShortcuts.html), [XTest](https://www.x.org/releases/X11R7.5/doc/man/man3/XTestFakeKeyEvent.3.html), [RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey), [UI Automation patterns](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-controlpatternsoverview), [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput)

## Decision

Keep state, text safety, and insertion outcomes in shared contracts. Implement platform adapters for shortcut, overlay, tray, focus, clipboard, and insertion. Linux prioritizes portal/Hyprland paths on Wayland, has a separate X11 backend, and falls back to copy-ready text. Windows prioritizes UI Automation, then verified clipboard/paste, then copy-only; direct Unicode injection is opt-in and never the sole recovery path.

## Tradeoffs

More adapter code and platform test matrices are required, but failures become explicit and user text is preserved across unsupported environments.

## Reversal cost

Low for domain logic; moderate for platform integration. Portable outcomes prevent UI/state rewrites if a new compositor or insertion technology is added.
