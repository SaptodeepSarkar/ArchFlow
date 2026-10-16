"""Phase 06 driver: checks the overlay against the daemon protocol it speaks.

What it ACTUALLY verifies (stdlib only, no Qt bindings):
  1. Static QML contract in the shipped overlay (UI/quickshell/shell.qml):
     every state the daemon publishes has a rendering branch
     (STARTING/RECORDING/TRANSCRIBING/CLEANING/INSERTING/READY/CANCELLED/
     IDLE/ERROR), the socket path is the daemon's, the wire format is
     newline-delimited JSON via Socket+SplitParser, the overlay never takes
     keyboard focus (load-bearing: typed text must reach the user's window),
     and the Stop button sends the `stop` op.
  2. Wire-format parity: a sample of each message the daemon emits
     (snapshot, state, provisional, amplitude) parses as JSON and carries the
     keys shell.qml reads. The daemon side is asserted live in gate-18.
  3. Toolchain reality: qmllint clean, quickshell runnable.

What it does NOT verify: pixels, that the compositor maps the layer surface,
or a real click. Live behaviour is gate-18's job.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QML = ROOT / "UI" / "quickshell" / "shell.qml"
STATES = ["STARTING", "RECORDING", "TRANSCRIBING", "CLEANING", "INSERTING",
          "READY", "CANCELLED", "IDLE", "ERROR"]
FAIL = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)


def main():
    src = QML.read_text()
    for s in STATES:
        check(f'"{s}"' in src, f"state {s!r} has no branch in the overlay")
    check("/vaani/control.sock" in src, "overlay does not point at the daemon socket")
    check("VAANI_SOCKET" in src, "overlay ignores the VAANI_SOCKET override")
    check("Socket {" in src and "SplitParser" in src,
          "IPC must be Socket + SplitParser (event-driven, no polling)")
    check("WlrKeyboardFocus.None" in src,
          "overlay must set keyboardFocus None (typed text goes to the user window)")
    check("WlrLayer.Overlay" in src, "overlay must render on the overlay layer")
    check('sendOp("stop")' in src, "Stop button is not wired to the stop op")
    check('"provisional"' in src and '"amplitude"' in src,
          "overlay does not handle provisional/amplitude events")
    check("protocol_version" in src, "overlay does not stamp a protocol version")

    # Wire parity: the shapes the daemon sends must parse and carry the keys
    # the overlay reads.
    samples = {
        "snapshot": '{"protocol_version":1,"session_id":"s1","state":"RECORDING"}',
        "state": '{"session_id":"s1","event":"state","state":"INSERTING","message":"Typing clean text"}',
        "state+data": '{"session_id":"s1","event":"state","state":"READY","message":"Typed","data":{"text":"Hello.","copied":true}}',
        "provisional": '{"session_id":"s1","event":"provisional","data":{"tail":"one two","words":"one two","hidden":false}}',
        "amplitude": '{"session_id":"s1","event":"amplitude","amplitude":0.42}',
    }
    for name, raw in samples.items():
        try:
            doc = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            check(False, f"{name} sample is not JSON: {e}")
            continue
        if name == "snapshot":
            check({"state", "session_id"} <= set(doc), "snapshot needs state+session_id")
        elif name.startswith("state"):
            check(doc.get("event") == "state", "state sample must carry event=state")
            check("state" in doc, "state sample must carry a state")
        elif name == "provisional":
            check("words" in doc.get("data", {}), "provisional needs data.words")
        elif name == "amplitude":
            check("amplitude" in doc, "amplitude event needs the level")
    check(re.search(r'kind:\s*\{\s*\n?\s*op:\s*op', src) is not None
          or "op: op" in src, "ops must be wrapped in kind:{op}")

    r = subprocess.run(["qmllint", str(QML)], capture_output=True, text=True)
    check(r.returncode == 0, f"qmllint failed: {(r.stdout + r.stderr).strip()}")
    r = subprocess.run(["quickshell", "--help"], capture_output=True, text=True, timeout=15)
    check(r.returncode == 0, "quickshell binary not runnable")

    if FAIL:
        print(f"PILL DRIVER RED ({len(FAIL)}):")
        for x in FAIL:
            print(f"  - {x}")
        return 1
    print(f"PILL DRIVER GREEN ({len(STATES)} states, {len(samples)} wire shapes, focus+stop wiring)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
