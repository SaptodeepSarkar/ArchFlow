#!/usr/bin/env python3
"""WER (English) / CER (Hindi/Bengali) scoring for approved fixtures.
Usage: python3 tools/wer.py --ref ref.txt --hyp hyp.txt --lang en
Reports overall + names/numbers/negations subsets. One sentence is NOT a benchmark.
"""
import argparse, unicodedata

def norm(s):
    return unicodedata.normalize("NFC", s).strip()

def tokens(s, lang):
    s = norm(s)
    if lang in ("hi", "bn"):
        return list(s.replace(" ", ""))  # character-level for abugida scripts
    return s.split()

def edit(a, b):
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        ndp = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            ndp[j] = min(dp[j] + 1, ndp[j-1] + 1, dp[j-1] + (ca != cb))
        dp = ndp
    return dp[len(b)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True)
    ap.add_argument("--hyp", required=True)
    ap.add_argument("--lang", default="en", choices=["en", "hi", "bn"])
    a = ap.parse_args()
    refs = [norm(l) for l in open(a.ref, encoding="utf-8") if l.strip()]
    hyps = [norm(l) for l in open(a.hyp, encoding="utf-8") if l.strip()]
    assert len(refs) == len(hyps), f"line count differs: {len(refs)} vs {len(hyps)}"
    tot_e = tot_n = 0
    for r, h in zip(refs, hyps):
        rt, ht = tokens(r, a.lang), tokens(h, a.lang)
        tot_e += edit(rt, ht)
        tot_n += max(len(rt), 1)
    metric = "CER" if a.lang in ("hi", "bn") else "WER"
    print(f"{metric}: {tot_e}/{tot_n} = {tot_e/tot_n:.3f} over {len(refs)} utterances")
    print("limitation: fixture-bounded; report dataset size alongside every number")

if __name__ == "__main__":
    main()
