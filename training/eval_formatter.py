#!/usr/bin/env python3
"""Formatter eval: EM, entity/number survival, precision-weighted token F0.5,
over-edit rate, punctuation and intensity-marker survival.

`predictions.jsonl` is written next to the summary so a bad number can be read
back to the exact pair that produced it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

import torch
from transformers import AutoTokenizer, Qwen2ForCausalLM

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|[^\sA-Za-z0-9]")
NUMBER_RE = re.compile(r"\d[\d.,:/%+-]*")
PROFANITY = {"damn", "hell", "shit", "fuck", "fucking", "bloody", "crap", "arse", "ass"}


def tokens(text):
    return [token.lower() for token in TOKEN_RE.findall(text)]


def final_punctuation(text):
    text = text.strip()
    return text[-1] if text and text[-1] in ".!?…" else ""


def normalise(text):
    return " ".join(tokens(text))


def token_f05(prediction, reference):
    """Multiset token F0.5 (beta=0.5 weights precision, i.e. over-editing)."""
    predicted, reference_tokens = Counter(tokens(prediction)), Counter(tokens(reference))
    overlap = sum((predicted & reference_tokens).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(predicted.values())
    recall = overlap / sum(reference_tokens.values())
    beta2 = 0.25
    return (1 + beta2) * precision * recall / (beta2 * precision + recall)


def required_tokens(row):
    """Contract tokens plus every number in the target must survive verbatim."""
    required = [str(token) for token in (row.get("protected_tokens") or [])]
    required += NUMBER_RE.findall(row["output"])
    return sorted(set(required))


def survived(output, token):
    if NUMBER_RE.fullmatch(token):
        return token in output
    return token.lower() in output.lower()


def intensity_markers(text):
    markers = set()
    if "!" in text:
        markers.add("!")
    for token in TOKEN_RE.findall(text):
        if token.isupper() and len(token) > 1:
            markers.add(f"caps:{token.lower()}")
        if token.lower() in PROFANITY:
            markers.add(f"word:{token.lower()}")
    return markers


def over_edit(input_text, prediction, reference):
    """Tokens the input already had right but the model changed anyway."""
    kept = Counter(tokens(input_text)) & Counter(tokens(reference))
    total = sum(kept.values())
    preserved = sum((Counter(tokens(prediction)) & kept).values())
    return total - preserved, total


def score(rows, predictions):
    scored = []
    required_total = required_kept = number_total = number_kept = 0
    sustained = 0
    marker_total = marker_kept = 0
    punct_ok = 0
    em = em_norm = 0
    edited_total = edited_wrong = 0
    edited_rows = 0

    for row, prediction in zip(rows, predictions):
        exact = prediction.strip() == row["output"].strip()
        em += int(exact)
        em_norm += int(normalise(prediction) == normalise(row["output"]))
        punct_ok += int(final_punctuation(prediction) == final_punctuation(row["output"]))
        row_f05 = token_f05(prediction, row["output"])
        sustained += row_f05

        for token in required_tokens(row):
            required_total += 1
            ok = survived(prediction, token)
            required_kept += int(ok)
            if NUMBER_RE.fullmatch(token) and token.isdigit():
                number_total += 1
                number_kept += int(ok)

        markers = intensity_markers(row["output"])
        if markers:
            marker_total += 1
            marker_kept += int(bool(markers & intensity_markers(prediction)))

        wrong, total = over_edit(row["input"], prediction, row["output"])
        edited_wrong += wrong
        edited_total += total
        edited_rows += int(wrong > 0)

        scored.append({
            "id": row.get("id"),
            "input": row["input"],
            "reference": row["output"],
            "prediction": prediction,
            "exact_match": exact,
            "token_f0_5": round(row_f05, 4),
            "protected_missing": [t for t in required_tokens(row) if not survived(prediction, t)],
        })

    n = len(scored)
    return scored, {
        "n": n,
        "exact_match": em / n,
        "exact_match_normalised": em_norm / n,
        "token_f0_5": sustained / n,
        "entity_survival": required_kept / required_total if required_total else 1.0,
        "number_survival": number_kept / number_total if number_total else 1.0,
        "over_edit_rate": edited_wrong / edited_total if edited_total else 0.0,
        "over_edit_row_rate": edited_rows / n,
        "punctuation_accuracy": punct_ok / n,
        "intensity_survival": marker_kept / marker_total if marker_total else 1.0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--eval-dir", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    device = args.device or ("cuda" if torch.cuda.is_available() else "cpu")
    eval_dir = args.eval_dir or os.path.join(os.path.dirname(os.path.abspath(args.data)), "eval")
    os.makedirs(eval_dir, exist_ok=True)

    rows = common.formatter_split(args.data, args.split)
    if args.limit:
        rows = rows[:args.limit]
    if not rows:
        raise SystemExit(f"no rows in {args.data}/formatter/{args.split}.jsonl")

    dtype = torch.float16 if device == "cuda" else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = Qwen2ForCausalLM.from_pretrained(
        args.model, torch_dtype=dtype, attn_implementation="sdpa").to(device).eval()
    model.config.use_cache = True

    predictions = []
    with torch.inference_mode():
        for row in rows:
            prompt = tokenizer.apply_chat_template(common.chat_messages(row)[:2], tokenize=False,
                                                   add_generation_prompt=True)
            ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(device)
            generated = model.generate(ids, max_new_tokens=args.max_new_tokens, do_sample=False,
                                       pad_token_id=tokenizer.pad_token_id)
            predictions.append(tokenizer.decode(generated[0][ids.shape[1]:],
                                                skip_special_tokens=True).strip())

    scored, report = score(rows, predictions)
    report.update({"model": args.model, "split": args.split})
    common.write_json(os.path.join(eval_dir, "formatter.json"), report)
    with open(os.path.join(eval_dir, "predictions.jsonl"), "w") as f:
        for row in scored:
            f.write(json.dumps(row) + "\n")
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in report.items()}),
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
