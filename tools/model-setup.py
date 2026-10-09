#!/usr/bin/env python3
"""First-run model setup: choose -> download to tmp -> sha256 verify -> atomic rename.
Usage: python3 tools/model-setup.py --model base --lang en
Models live in $XDG_DATA_HOME/vaani/models (never bundled, never at install).
"""
import argparse, hashlib, os, sys, tempfile, urllib.request

MODEL_REVISION = "c521a4b02f422512d734391fdf08bb08c0862f68"
MANIFEST = {
    "tiny":    ("ggml-tiny.bin", 75_975_616, "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21"),
    "base":    ("ggml-base.bin", 147_951_465, "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"),
    "base.en": ("ggml-base.en.bin", 147_964_211, "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"),
    "small":   ("ggml-small.bin", 487_626_665, "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"),
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
    ap.add_argument("--sha256", help="optional checksum assertion; must match the pinned manifest")
    a = ap.parse_args()
    filename, want, expected_hash = MANIFEST[a.model]
    url = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/{MODEL_REVISION}/{filename}"
    if a.sha256 and a.sha256.lower() != expected_hash:
        print("provided checksum does not match the pinned model manifest", file=sys.stderr)
        return 2
    dest = os.path.join(models_dir(), f"{a.model}.bin")
    if os.path.exists(dest) and os.path.getsize(dest) == want:
        h = hashlib.sha256()
        with open(dest, "rb") as existing:
            for block in iter(lambda: existing.read(1 << 20), b""):
                h.update(block)
        if h.hexdigest() == expected_hash:
            print(f"already present and verified: {dest}")
            return 0
        print("existing model checksum mismatch; replacing it", file=sys.stderr)
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
        if h.hexdigest() != expected_hash:
            print("checksum mismatch — refusing to install", file=sys.stderr)
            return 1
        print("sha256 OK")
        os.rename(tmp, dest)  # atomic install
        print(f"installed: {dest}")
        return 0
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

if __name__ == "__main__":
    sys.exit(main())
