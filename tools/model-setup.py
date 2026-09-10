#!/usr/bin/env python3
"""First-run model setup: choose -> download to tmp -> sha256 verify -> atomic rename.
Usage: python3 tools/model-setup.py --model base --lang en
Models live in $XDG_DATA_HOME/vaani/models (never bundled, never at install).
"""
import argparse, hashlib, os, sys, tempfile, urllib.request

MANIFEST = {
    # url template + expected bytes; sha256 filled after pin verification
    # (see models/manifest.toml). Downloads refused on mismatch.
    "tiny":    ("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin", 75_975_616),
    "base":    ("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin", 147_964_211),
    "base.en": ("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin", 147_964_211),
    "small":   ("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin", 487_626_665),
}

def models_dir():
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    d = os.path.join(base, "vaani", "models")
    os.makedirs(d, exist_ok=True)
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="base", choices=list(MANIFEST))
    ap.add_argument("--lang", default="en", choices=["en", "hi", "bn"])
    ap.add_argument("--sha256", default="", help="expected checksum; empty skips verification with a warning")
    a = ap.parse_args()
    url, want = MANIFEST[a.model]
    dest = os.path.join(models_dir(), f"{a.model}.bin")
    if os.path.exists(dest) and os.path.getsize(dest) == want:
        print(f"already present: {dest}")
        return 0
    print(f"downloading {a.model} ({want/1e6:.0f} MB) for lang={a.lang} ...")
    print("source: huggingface.co/ggerganov/whisper.cpp | license: MIT")
    fd, tmp = tempfile.mkstemp(prefix="vaani-model-", dir=models_dir())
    try:
        h = hashlib.sha256()
        got = 0
        with os.fdopen(fd, "wb") as f, urllib.request.urlopen(url) as r:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
                h.update(b)
                got += len(b)
                print(f"\r  {got/1e6:.1f}/{want/1e6:.0f} MB", end="", flush=True)
        print()
        if got != want:
            print(f"size mismatch: got {got}, want {want}", file=sys.stderr)
            return 1
        if a.sha256:
            if h.hexdigest() != a.sha256.lower():
                print("checksum mismatch — refusing to install", file=sys.stderr)
                return 1
            print("sha256 OK")
        else:
            print("WARNING: no --sha256 given; skipping verification (not recommended)")
        os.rename(tmp, dest)  # atomic install
        print(f"installed: {dest}")
        return 0
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

if __name__ == "__main__":
    sys.exit(main())
