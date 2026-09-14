#!/usr/bin/env python3
"""Train/evaluate a tiny non-generative Vaani edit-plan classifier baseline."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import torch
from torch import nn


OPS = ["preserve", "punctuate", "grammar", "make_list", "numbered_list", "emoji", "format_only"]
STRUCTURES = ["sentence", "list", "numbered_list"]
SPEECH = ["statement", "question", "emoji", "command_as_data"]
DIM = 4096


def features(text: str) -> torch.Tensor:
    text = text.lower()
    vals = [0.0] * DIM
    units = re.findall(r"[a-z0-9_./:-]+", text)
    units += [text[i:i + 3] for i in range(max(0, len(text) - 2))]
    for unit in units:
        digest = hashlib.blake2b(unit.encode(), digest_size=4).digest()
        index = int.from_bytes(digest, "little") % DIM
        vals[index] += 1.0
    vector = torch.tensor(vals)
    return vector / vector.norm().clamp_min(1.0)


def classify_labels(source: str, target: dict) -> dict:
    low = source.lower()
    op = target.get("operation", "format_only")
    structure = "numbered_list" if op == "numbered_list" else "list" if op == "make_list" else "sentence"
    speech = "emoji" if op == "emoji" else "question" if low.startswith(("where ", "what ", "why ", "when ", "who ", "how ")) else "statement"
    if re.match(r"\s*(open|install|delete|send|run)\b", source, re.I):
        speech = "command_as_data"
    protected = sorted(set(re.findall(r"\b(?:CUDA|MCP|HTML|CSS|CTC|GitHub|[A-Z][A-Za-z0-9_-]{2,})\b", source)))
    return {"operation": op, "speech_act": speech, "structure": structure,
            "protected_terms": protected,
            "needs_confirmation": bool(target.get("needs_confirmation", False))}


class EditClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(DIM, 96), nn.ReLU(), nn.Dropout(.1))
        self.operation = nn.Linear(96, len(OPS))
        self.structure = nn.Linear(96, len(STRUCTURES))
        self.speech = nn.Linear(96, len(SPEECH))
        self.confirmation = nn.Linear(96, 2)

    def forward(self, x):
        h = self.body(x)
        return self.operation(h), self.structure(h), self.speech(h), self.confirmation(h)


def read_rows(paths):
    rows = []
    for path in paths:
        rows.extend(json.loads(line) for line in Path(path).read_text().splitlines() if line.strip())
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, nargs="+", required=True)
    ap.add_argument("--eval", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=500)
    args = ap.parse_args()
    train = read_rows(args.train)
    eval_rows = [json.loads(line) for line in args.eval.read_text().splitlines() if line.strip()]
    model = EditClassifier()
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss()
    x = torch.stack([features(row["input"]) for row in train])
    labels = [classify_labels(row["input"], json.loads(row["output"])) for row in train]
    y = (torch.tensor([OPS.index(row["operation"]) for row in labels]),
         torch.tensor([STRUCTURES.index(row["structure"]) for row in labels]),
         torch.tensor([SPEECH.index(row["speech_act"]) for row in labels]),
         torch.tensor([int(row["needs_confirmation"]) for row in labels]))
    model.train()
    for _ in range(args.epochs):
        pred = model(x)
        loss = sum(loss_fn(a, b) for a, b in zip(pred, y))
        opt.zero_grad(); loss.backward(); opt.step()
    model.eval()
    results = []
    with torch.inference_mode():
        for row in eval_rows:
            out = model(features(row["input"]).unsqueeze(0))
            op, structure, speech, confirmation = [int(v.argmax(-1).item()) for v in out]
            got = {"operation": OPS[op], "speech_act": SPEECH[speech],
                   "structure": STRUCTURES[structure],
                   "protected_terms": sorted(set(re.findall(r"\b(?:CUDA|MCP|HTML|CSS|CTC|GitHub|[A-Z][A-Za-z0-9_-]{2,})\b", row["input"]))),
                   "needs_confirmation": bool(confirmation)}
            expected = json.loads(row["output"])
            results.append({"input": row["input"], "expected": row["output"],
                            "generated": json.dumps(got, ensure_ascii=False, separators=(",", ":")),
                            "valid": True, "exact": got == expected})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), args.out / "model.pt")
    (args.out / "config.json").write_text(json.dumps({"dim": DIM, "operations": OPS,
                                                       "structures": STRUCTURES, "speech": SPEECH}))
    report = args.out / "eval.jsonl"
    report.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results))
    print(json.dumps({"count": len(results), "exact": sum(r["exact"] for r in results),
                      "out": str(args.out), "eval": str(report)}))


if __name__ == "__main__":
    main()
