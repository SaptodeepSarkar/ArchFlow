#!/usr/bin/env python3
"""Phase 14 soak driver (stdlib only).

Scripted soak: LOOPS x PER_LOOP sentences through format+type by reusing
TESTS/drivers/run_loop.sh --raw (the accelerated, no-audio path through the
same llm-format + type-text stages). Stub wtype comes from the caller's PATH
(run_loop.sh refuses to run unless wtype resolves to $VAANI_WTYPE_STUB).

Gibberish soak: 15 curated + 100 seeded fuzz inputs through the same stages
(llm-format, then type-text only when formatting yields text). Each input is
declined (formatter returns empty -> nothing typed, a noop) or harmless
(typed byte-identical to formatted and free of DENYLIST action semantics).

Writes a JSON summary (--summary) and prints a counts table. Threshold
decisions belong to TESTS/gates/gate-14.sh; this driver only reports.
"""
import argparse
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

# Destructive action semantics Vaani must never emit: it has no volume,
# brightness, power, shell, or window-kill actions, so none of these may
# ever appear in formatted/typed output. Inputs below deliberately avoid
# these tokens, so any hit means the formatter hallucinated an action.
DENYLIST = [
    "rm -rf", "shutdown", "poweroff", "reboot", "mkfs",
    "dd if=", ":(){", "kill -9", "taskkill",
    "volume-max", "volume max", "brightness-0", "brightness 0",
    "format c:", "del /f",
]

CURATED_GIBBERISH = [
    "",  # empty
    "   ",  # whitespace-only
    "!!!",
    "??? ... !!!",
    "asdf qwer zxcv",
    "qwertyuiop asdfghjkl zxcvbnm",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "uh umm hmm like you know",  # filler-only, expect decline
    "zzzzzzzzzz 1234567890 !@#$%^",
    "hello world cafe naive resume",  # plain words, no accents to stay argv-safe
    "lorem ipsum dolor sit amet " * 20,  # very long
    ",,, ... --- ///",
    "no no no no no no",
    "blah blah blah blah",
    "xkcd qzx jwv bfp vmrk",
]

FUZZ_POOL = [
    "uh", "umm", "hmm", "like", "so", "well", "blah", "zorp", "qwex",
    "asdf", "zxcv", "qwer", "plugh", "xyzzy", "mumble", "thingy",
    "123", "42", "007", "hello", "no", "yes", "maybe",
    "!", "?", ".", ",", "...", "---", "///", "@", "#", "%", "&", "*",
    "aaa", "zzz", "mmm", "ooo", "qqq",
]


def build_fuzz(seed, count):
    rng = random.Random(seed)
    out = []
    guard = 0
    while len(out) < count and guard < count * 20:
        guard += 1
        n = rng.randint(1, 12)
        text = " ".join(rng.choice(FUZZ_POOL) for _ in range(n))
        if not text.strip():
            continue
        low = text.lower()
        if any(d in low for d in DENYLIST):
            continue
        out.append(text)
    return out


def run_loop(outdir, name, raw, llm_format, type_text, transcribe):
    """One scripted sentence via run_loop.sh. Returns (rc, tail_state)."""
    env = dict(os.environ)
    env["LLM_FORMAT"] = llm_format
    env["TYPE_TEXT"] = type_text
    env["TRANSCRIBE"] = transcribe
    p = subprocess.run(
        [os.path.join(HERE, "run_loop.sh"), outdir, name, "--raw", raw],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=env, text=True, timeout=120,
    )
    tail = ""
    try:
        with open(os.path.join(outdir, name + ".states.log")) as f:
            lines = f.read().splitlines()
        tail = lines[-1] if lines else "<empty>"
    except OSError:
        tail = "<missing>"
    return p.returncode, tail, p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""


def run_stage(outdir, name, raw, llm_format, type_text):
    """Gibberish input through the run_loop stages, tolerating decline.

    Returns (verdict, detail) with verdict in
    declined | harmless | flagged | crash.
    """
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, name + ".raw.txt"), "w") as f:
        f.write(raw)
    try:
        p = subprocess.run(
            [llm_format], input=raw + "\n",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return "crash", "llm-format did not return: %s" % e
    if p.returncode != 0:
        return "crash", "llm-format rc=%d: %s" % (p.returncode, p.stderr.strip()[:200])
    fmt = p.stdout.strip()
    with open(os.path.join(outdir, name + ".formatted.txt"), "w") as f:
        f.write(fmt)
    if not fmt:
        return "declined", "formatter returned empty, nothing typed"
    low = fmt.lower()
    hit = next((d for d in DENYLIST if d in low), None)
    if hit:
        return "flagged", "denylist hit %r in formatted output" % hit
    scratch = os.path.join(outdir, name + ".scratch")
    env = dict(os.environ)
    env["VAANI_WTYPE_SCRATCH"] = scratch
    try:
        t = subprocess.run(
            [type_text, "--pill-hidden", fmt],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, text=True, timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return "crash", "type-text did not return: %s" % e
    if t.returncode != 0:
        return "crash", "type-text rc=%d" % t.returncode
    try:
        with open(scratch) as f:
            typed = f.read()
    except OSError as e:
        return "crash", "no scratch capture: %s" % e
    with open(os.path.join(outdir, name + ".typed.txt"), "w") as f:
        f.write(typed)
    if typed != fmt:
        return "crash", "typed != formatted (%d vs %d bytes)" % (len(typed), len(fmt))
    if any(d in typed.lower() for d in DENYLIST):
        return "flagged", "denylist hit in typed output"
    return "harmless", "typed %d bytes, denylist clean" % len(typed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--loops", type=int, default=3)
    ap.add_argument("--per-loop", type=int, default=75)
    ap.add_argument("--seed", type=int, default=14)
    ap.add_argument("--summary", required=True)
    a = ap.parse_args()

    llm_format = os.environ.get("LLM_FORMAT", os.path.join(ROOT, "target", "debug", "llm-format"))
    type_text = os.environ.get("TYPE_TEXT", os.path.join(ROOT, "target", "debug", "type-text"))
    transcribe = os.environ.get("TRANSCRIBE", os.path.join(ROOT, "target", "debug", "transcribe"))
    for b in (llm_format, type_text):
        if not (os.path.isfile(b) and os.access(b, os.X_OK)):
            print("soak: binary missing: %s" % b, file=sys.stderr)
            return 2

    with open(os.path.join(ROOT, "TESTS", "fixtures", "formatting.json")) as f:
        fixtures = json.load(f)
    raws = [p["raw"] for p in fixtures]
    want = {p["raw"]: p["expected"] for p in fixtures}

    loops_dir = os.path.join(a.outdir, "loops")
    gib_dir = os.path.join(a.outdir, "gibberish")
    os.makedirs(loops_dir, exist_ok=True)
    os.makedirs(gib_dir, exist_ok=True)

    scripted = {"total": 0, "ok": 0, "crashes": 0, "stuck": 0, "mismatch": 0}
    failures = []
    for li in range(a.loops):
        for si in range(a.per_loop):
            raw = raws[(li * a.per_loop + si) % len(raws)]
            name = "loop%d-s%03d" % (li, si)
            scripted["total"] += 1
            try:
                rc, tail, _ = run_loop(loops_dir, name, raw, llm_format, type_text, transcribe)
            except (OSError, subprocess.TimeoutExpired) as e:
                rc, tail = 1, "<driver-error %s>" % e
            idle = (tail == "state=idle offloaded")
            if rc == 0 and idle:
                # Fixture-derived raws should also match the expected text.
                try:
                    with open(os.path.join(loops_dir, name + ".typed.txt")) as f:
                        typed = f.read()
                except OSError:
                    typed = None
                if typed != want.get(raw):
                    scripted["mismatch"] += 1
                    failures.append("%s: typed %r != expected %r" % (name, typed, want.get(raw)))
                else:
                    scripted["ok"] += 1
            else:
                if rc != 0:
                    scripted["crashes"] += 1
                if not idle:
                    scripted["stuck"] += 1
                failures.append("%s: rc=%d tail=%r" % (name, rc, tail))

    gib_inputs = list(CURATED_GIBBERISH) + build_fuzz(a.seed, 100)
    gib = {"total": len(gib_inputs), "declined": 0, "harmless": 0,
           "flagged": 0, "crashes": 0}
    for i, raw in enumerate(gib_inputs):
        name = "gib-%03d" % i
        verdict, detail = run_stage(gib_dir, name, raw, llm_format, type_text)
        gib[verdict] += 1
        if verdict in ("flagged", "crash"):
            failures.append("%s: %s input=%r" % (name, detail, raw[:80]))

    summary = {
        "loops": a.loops, "per_loop": a.per_loop, "seed": a.seed,
        "scripted": scripted, "gibberish": gib, "failures": failures[:20],
    }
    with open(a.summary, "w") as f:
        json.dump(summary, f, indent=2)

    print("counts: scripted_total=%d ok=%d crashes=%d stuck=%d mismatch=%d" % (
        scripted["total"], scripted["ok"], scripted["crashes"],
        scripted["stuck"], scripted["mismatch"]))
    print("counts: gibberish_total=%d declined=%d harmless=%d flagged=%d crashes=%d" % (
        gib["total"], gib["declined"], gib["harmless"], gib["flagged"], gib["crashes"]))
    print("counts: noop=%d (gibberish declined)" % gib["declined"])
    if failures:
        print("first failures:")
        for line in failures[:10]:
            print("  %s" % line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
