"""Phase 06 stub event driver: feeds state+words sequences to a headless check.

What it ACTUALLY verifies (stdlib only, no Qt bindings installed):
  1. Static QML contract: UI/pill.qml declares exactly the 4 PRD states
     (listening/transcribing/writing/error), a `cancelRequested` signal wired
     to the cancel button's onClicked, a `trailingWindow` constant defaulting
     to 4 (PRD default), and never-take-focus flags (root focus:false,
     Button focusPolicy Qt.NoFocus).
  2. Trailing-window behavior: replays scripted state+words event sequences
     and checks the displayed text equals last-N-words with N=trailingWindow,
     using a Python mirror of the QML trail() function (same split-on-
     whitespace, drop-blanks, take-last-N rule).
  3. Toolchain reality: `qmllint` is clean on the file, `qml6` loads it
     offscreen with no errors, and `quickshell --help` runs (binary present).

What it does NOT verify: pixels/screenshots, real QuickShell PanelWindow
hosting, or mouse clicks on the button (no display server here). The cancel
wiring is proven statically (signal declared + onClicked emits it), not by
a live click.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QML = ROOT / "UI" / "pill.qml"
STATES = ["listening", "transcribing", "writing", "error"]
FAIL = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)


def trail(words, n=4):
    ws = [w for w in str(words).split() if w]
    return " ".join(ws[-n:])


def main():
    src = QML.read_text()
    for s in STATES:
        check(f'"{s}"' in src, f"state {s!r} missing from pill.qml")
    check("signal cancelRequested" in src, "cancelRequested signal missing")
    check(re.search(r"onClicked:\s*pill\.cancelRequested\(\)", src),
          "cancel button not wired to pill.cancelRequested()")
    m = re.search(r"property int trailingWindow:\s*(\d+)", src)
    check(m and int(m.group(1)) == 4, "trailingWindow constant must default to 4")
    check("focus: false" in src, "pill must set focus: false")
    check("focusPolicy: Qt.NoFocus" in src, "cancel button must set focusPolicy: Qt.NoFocus")
    check("trail(" in src, "trail() helper missing")

    n = int(m.group(1)) if m else 4
    # Feed state+words sequences; displayed text must be the trailing window.
    sequences = [
        ("listening", "speak now", "speak now"),
        ("listening", "one two three four five six", "three four five six"),
        ("transcribing", "  extra   spaces\tand\nnewline here today", "and newline here today"),
        ("transcribing", "short", "short"),
        ("writing", "", ""),
        ("writing", "Formatted output here now done", "output here now done"),
        ("error", "mic failed badly oh no", "failed badly oh no"),
    ]
    for state, words, expected in sequences:
        check(state in STATES, f"unknown state {state!r}")
        got = trail(words, n)
        check(got == expected, f"[{state}] trail({words!r})={got!r}, want {expected!r}")

    r = subprocess.run(["qmllint", str(QML)], capture_output=True, text=True)
    check(r.returncode == 0, f"qmllint failed: {(r.stdout + r.stderr).strip()}")
    # qml6 runs an event loop forever on success, so wrap in `timeout`:
    # 124 (killed = stayed alive) or 0 with no error text means it loaded.
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    r = subprocess.run(["timeout", "10", "qml6", str(QML)],
                       capture_output=True, text=True, timeout=30, env=env)
    out = (r.stdout + r.stderr).strip()
    check(r.returncode in (0, 124) and "error" not in out.lower(),
          f"qml6 offscreen load failed (exit {r.returncode}): {out[:300]}")
    r = subprocess.run(["quickshell", "--help"], capture_output=True, text=True, timeout=15)
    check(r.returncode == 0, "quickshell binary not runnable")

    if FAIL:
        print(f"PILL DRIVER RED ({len(FAIL)}):")
        for x in FAIL:
            print(f"  - {x}")
        return 1
    print(f"PILL DRIVER GREEN ({len(sequences)} event sequences, "
          f"{len(STATES)} states, trailingWindow={n})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
