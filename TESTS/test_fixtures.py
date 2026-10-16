"""Gate 01: formatting fixtures + repo contracts. stdlib only; doubles as gate.sh 01."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "fixtures" / "formatting.json"
FAIL = []


def check(cond, msg):
    if not cond:
        FAIL.append(msg)


def main():
    pairs = json.loads(FIX.read_text())
    check(isinstance(pairs, list) and len(pairs) >= 20, "need >=20 fixture pairs")
    ids = [p.get("id") for p in pairs]
    check(len(set(ids)) == len(ids), "fixture ids must be unique")
    for p in pairs:
        check(p.get("raw") and p.get("expected"), f"{p.get('id')}: raw+expected required")
        exp = p.get("expected", "")
        check("umm" not in exp.lower() and "hmm" not in exp.lower(), f"{p.get('id')}: filler leaked")
        check(exp[:1].isupper(), f"{p.get('id')}: expected must start capitalized")
        check(exp[-1] in ".?!…", f"{p.get('id')}: expected must end with punctuation")
    # repo contracts every phase relies on
    for f in ["PRD/overview.md", "DOCS/architecture.md", "UI/pill.qml"]:
        check((ROOT.parent / f).exists(), f"missing {f}")

    if FAIL:
        print(f"GATE 01 RED ({len(FAIL)}):")
        for m in FAIL:
            print(f"  - {m}")
        return 1
    print(f"GATE 01 GREEN ({len(pairs)} fixtures, contracts ok)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
