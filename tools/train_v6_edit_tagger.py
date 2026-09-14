#!/usr/bin/env python3
"""Train a small source-grounded V6 edit/tag baseline.

This is intentionally a bounded tagger, not a text generator. It predicts
token actions and closed sentence-level labels. Rendering remains deterministic
and is a separate concern.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

# Set these before importing torch so BLAS libraries cannot fan out during
# initialization. The CLI still clamps torch's own thread pools below.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

TOKEN_LABELS = ["KEEP", "DELETE_FILLER", "DELETE_FALSE_START", "DELETE_RETRACTED", "CAPITALIZE", "NORMALIZE_ALLOWED"]
STRUCTURES = ["PROSE", "UNORDERED_LIST", "ORDERED_LIST"]
SPEECH = ["STATEMENT", "QUESTION", "EXCLAMATION", "FRAGMENT", "COMMAND_AS_DATA"]
EMOJIS = ["NONE", "LAUGH", "THUMBS_UP", "CELEBRATION", "HEART", "OTHER_SUPPORTED"]
PUNCT = ["NONE", "COMMA", "PERIOD", "QUESTION_MARK", "EXCLAMATION_MARK", "COLON", "SEMICOLON"]
BUCKETS = 2048
MAX_FEATURES = 10
TOKEN_RE = re.compile(r"https?://[^\s]+|/[^\s]+|[A-Za-z0-9_][A-Za-z0-9_.-]*|[^\w\s]")


def hash_id(value: str) -> int:
    return int.from_bytes(hashlib.blake2b(value.encode(), digest_size=4).digest(), "little") % BUCKETS


def token_features(tokens: list[str], i: int) -> list[int]:
    t = tokens[i].lower()
    units = ["tok=" + t, "pos=" + str(min(i, 7)), "len=" + str(min(len(t), 12))]
    if i: units.append("prev=" + tokens[i - 1].lower())
    if i + 1 < len(tokens): units.append("next=" + tokens[i + 1].lower())
    units.extend("c3=" + t[j:j + 3] for j in range(max(0, len(t) - 2)))
    return [hash_id(x) for x in units[:MAX_FEATURES]]


class Rows(Dataset):
    def __init__(self, rows: list[dict], max_len: int):
        self.rows, self.max_len = rows, max_len

    def __len__(self): return len(self.rows)

    def __getitem__(self, i):
        r = self.rows[i]; ts = r["source_tokens"][:self.max_len]
        feats = torch.zeros((self.max_len, MAX_FEATURES), dtype=torch.long)
        mask = torch.zeros(self.max_len)
        for j in range(len(ts)):
            fs = token_features(ts, j); feats[j, :len(fs)] = torch.tensor(fs); mask[j] = 1
        tok = torch.full((self.max_len,), -100, dtype=torch.long)
        tok[:len(ts)] = torch.tensor([TOKEN_LABELS.index(x) for x in r["token_labels"][:self.max_len]])
        punct = torch.zeros(self.max_len, dtype=torch.long)
        for j, value in r["punctuation_after"].items():
            if int(j) < self.max_len: punct[int(j)] = PUNCT.index(value)
        return feats, mask, tok, punct, STRUCTURES.index(r["structure"]), SPEECH.index(r["speech_act"]), EMOJIS.index(r["emoji_intent"])


class Tagger(nn.Module):
    def __init__(self, hidden: int = 96):
        super().__init__()
        self.embedding = nn.Embedding(BUCKETS, hidden)
        self.body = nn.Sequential(nn.Linear(hidden, hidden), nn.ReLU(), nn.Dropout(.1))
        self.token = nn.Linear(hidden, len(TOKEN_LABELS))
        self.punct = nn.Linear(hidden, len(PUNCT))
        self.structure = nn.Linear(hidden, len(STRUCTURES))
        self.speech = nn.Linear(hidden, len(SPEECH))
        self.emoji = nn.Linear(hidden, len(EMOJIS))

    def forward(self, feats, mask):
        h = self.embedding(feats).sum(2)
        h = self.body(h)
        pooled = (h * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True).clamp_min(1)
        return self.token(h), self.punct(h), self.structure(pooled), self.speech(pooled), self.emoji(pooled)


class BiGRUTagger(nn.Module):
    """Small contextual encoder; labels and rendering remain unchanged."""
    def __init__(self, hidden: int = 96):
        super().__init__()
        self.embedding = nn.Embedding(BUCKETS, hidden)
        self.encoder = nn.GRU(hidden, hidden, num_layers=2, batch_first=True,
                               bidirectional=True, dropout=.1)
        width = hidden * 2
        self.token = nn.Linear(width, len(TOKEN_LABELS))
        self.punct = nn.Linear(width, len(PUNCT))
        self.structure = nn.Linear(width, len(STRUCTURES))
        self.speech = nn.Linear(width, len(SPEECH))
        self.emoji = nn.Linear(width, len(EMOJIS))

    def forward(self, feats, mask):
        h = self.embedding(feats).sum(2)
        h, _ = self.encoder(h)
        pooled = (h * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True).clamp_min(1)
        return self.token(h), self.punct(h), self.structure(pooled), self.speech(pooled), self.emoji(pooled)


class CausalConvTagger(nn.Module):
    """Low-latency causal context encoder for incremental formatter decisions."""
    def __init__(self, hidden: int = 96):
        super().__init__()
        self.embedding = nn.Embedding(BUCKETS, hidden)
        self.conv1 = nn.Conv1d(hidden, hidden, kernel_size=5)
        self.conv2 = nn.Conv1d(hidden, hidden, kernel_size=5, dilation=2)
        self.dropout = nn.Dropout(.1)
        self.token = nn.Linear(hidden, len(TOKEN_LABELS))
        self.punct = nn.Linear(hidden, len(PUNCT))
        self.structure = nn.Linear(hidden, len(STRUCTURES))
        self.speech = nn.Linear(hidden, len(SPEECH))
        self.emoji = nn.Linear(hidden, len(EMOJIS))

    def forward(self, feats, mask):
        h = self.embedding(feats).sum(2).transpose(1, 2)
        residual = h
        h = torch.relu(self.conv1(torch.nn.functional.pad(h, (4, 0))))
        h = self.dropout(h)
        h = torch.relu(self.conv2(torch.nn.functional.pad(h, (8, 0)))) + residual
        h = h.transpose(1, 2)
        pooled = (h * mask.unsqueeze(-1)).sum(1) / mask.sum(1, keepdim=True).clamp_min(1)
        return self.token(h), self.punct(h), self.structure(pooled), self.speech(pooled), self.emoji(pooled)


def load(paths: list[Path]) -> list[dict]:
    rows = []
    for path in paths:
        rows.extend(json.loads(x) for x in path.read_text().splitlines() if x.strip())
    return rows


def memory_mb() -> tuple[int, int]:
    available = 0
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            available = int(line.split()[1]) // 1024
            break
    rss = int(Path("/proc/self/status").read_text().split("VmRSS:", 1)[1].split()[0]) // 1024
    return available, rss


def memory_guard(stage: str, min_available_mb: int, max_rss_mb: int) -> None:
    available, rss = memory_mb()
    if available < min_available_mb or rss > max_rss_mb:
        print(json.dumps({"aborted": "memory_guard", "stage": stage,
                          "available_mb": available, "rss_mb": rss,
                          "min_available_mb": min_available_mb,
                          "max_rss_mb": max_rss_mb}))
        raise SystemExit(2)


def evaluate(model: nn.Module, rows: list[dict], max_len: int, batch_size: int,
             min_available_mb: int, max_rss_mb: int, stage: str) -> tuple[list[dict], dict]:
    model.eval(); results = []; offset = 0
    loader = DataLoader(Rows(rows, max_len), batch_size=batch_size, num_workers=0)
    with torch.inference_mode():
        for feats, mask, tok, punct, structure, speech, emoji in loader:
            memory_guard(stage, min_available_mb, max_rss_mb)
            pred = model(feats, mask)
            batch_rows = rows[offset:offset + len(feats)]; offset += len(feats)
            for b, r in enumerate(batch_rows):
                n = int(mask[b].sum())
                got_tok = [TOKEN_LABELS[int(x)] for x in pred[0][b, :n].argmax(-1)]
                got_punct = {str(i): PUNCT[int(x)] for i, x in enumerate(pred[1][b, :n].argmax(-1)) if int(x)}
                got = {"token_labels": got_tok, "punctuation_after": got_punct,
                       "structure": STRUCTURES[int(pred[2][b].argmax())],
                       "speech_act": SPEECH[int(pred[3][b].argmax())],
                       "emoji_intent": EMOJIS[int(pred[4][b].argmax())]}
                expected = {"token_labels": r["token_labels"],
                            "punctuation_after": r["punctuation_after"],
                            "structure": r["structure"],
                            "speech_act": r["speech_act"],
                            "emoji_intent": r["emoji_intent"]}
                token_correct = sum(a == b for a, b in zip(got_tok, expected["token_labels"]))
                results.append({"id": r["id"], "source": r["source"],
                                "expected": expected, "generated": got,
                                "token_correct": token_correct,
                                "token_count": len(expected["token_labels"]),
                                "exact": got == expected})
    tokens = sum(x["token_count"] for x in results)
    return results, {
        "rows": len(results),
        "exact": sum(x["exact"] for x in results),
        "exact_rate": sum(x["exact"] for x in results) / max(1, len(results)),
        "token_accuracy": sum(x["token_correct"] for x in results) / max(1, tokens),
    }


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--train", type=Path, nargs="+", required=True); ap.add_argument("--dev", type=Path, required=True); ap.add_argument("--test", type=Path, required=True); ap.add_argument("--out", type=Path, required=True); ap.add_argument("--epochs", type=int, default=20); ap.add_argument("--batch-size", type=int, default=16); ap.add_argument("--threads", type=int, default=1); ap.add_argument("--model", choices=("hashed", "bigru", "conv"), default="hashed"); ap.add_argument("--weighted", action="store_true"); ap.add_argument("--min-available-mb", type=int, default=4096); ap.add_argument("--max-rss-mb", type=int, default=2048)
    args = ap.parse_args(); memory_guard("before_load", args.min_available_mb, args.max_rss_mb); train, dev, test = load(args.train), load([args.dev]), load([args.test]); memory_guard("after_load", args.min_available_mb, args.max_rss_mb)
    # Keep the trainer safe alongside the desktop session. PyTorch's default
    # BLAS/OpenMP fan-out can multiply memory use. Higher parallelism requires
    # an explicit, measured opt-in.
    threads = max(1, min(args.threads, 2))
    torch.set_num_threads(threads)
    torch.set_num_interop_threads(1)
    batch_size = max(1, min(args.batch_size, 32))
    max_len = max(len(r["source_tokens"]) for r in train + dev + test)
    model = BiGRUTagger() if args.model == "bigru" else CausalConvTagger() if args.model == "conv" else Tagger(); opt = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    losses = [nn.CrossEntropyLoss(ignore_index=-100), nn.CrossEntropyLoss(), nn.CrossEntropyLoss(), nn.CrossEntropyLoss(), nn.CrossEntropyLoss()]
    if args.weighted:
        def weights(values, names):
            counts = {name: 0 for name in names}
            for value in values: counts[value] += 1
            raw = torch.tensor([(sum(counts.values()) / max(1, counts[name])) ** 0.5 for name in names], dtype=torch.float32).clamp_max(6.0)
            return raw / raw.mean()
        token_values = [v for row in train for v in row["token_labels"]]
        punct_values = [row["punctuation_after"].get(str(i), "NONE") for row in train for i in range(len(row["source_tokens"]))]
        losses[0] = nn.CrossEntropyLoss(weight=weights(token_values, TOKEN_LABELS), ignore_index=-100)
        losses[1] = nn.CrossEntropyLoss(weight=weights(punct_values, PUNCT))
    train_loader = DataLoader(Rows(train, max_len), batch_size=batch_size, shuffle=True, num_workers=0)
    best_state = None; best_key = (-1.0, -1.0); best_dev = {}; best_epoch = 0
    for epoch in range(args.epochs):
        model.train(); total = 0.0
        for feats, mask, tok, punct, structure, speech, emoji in train_loader:
            memory_guard(f"train_epoch_{epoch + 1}", args.min_available_mb, args.max_rss_mb)
            pred = model(feats, mask)
            loss = losses[0](pred[0].transpose(1, 2), tok) + losses[1](pred[1].transpose(1, 2), punct) + losses[2](pred[2], structure) + losses[3](pred[3], speech) + losses[4](pred[4], emoji)
            opt.zero_grad(); loss.backward(); opt.step(); total += float(loss.detach())
        dev_results, dev_metrics = evaluate(model, dev, max_len, batch_size, args.min_available_mb, args.max_rss_mb, f"dev_epoch_{epoch + 1}")
        key = (dev_metrics["exact_rate"], dev_metrics["token_accuracy"])
        if key > best_key:
            best_key = key; best_dev = dev_metrics; best_epoch = epoch + 1
            best_state = {name: value.detach().clone() for name, value in model.state_dict().items()}
        if epoch in (0, args.epochs - 1) or key == best_key:
            print(json.dumps({"epoch": epoch + 1, "loss": total / max(1, len(train_loader)), "dev": dev_metrics, "best_epoch": best_epoch}))
    if best_state is not None: model.load_state_dict(best_state)
    results, test_metrics = evaluate(model, test, max_len, batch_size, args.min_available_mb, args.max_rss_mb, "test")
    args.out.mkdir(parents=True, exist_ok=True); torch.save(model.state_dict(), args.out / "model.pt"); (args.out / "config.json").write_text(json.dumps({"model": args.model, "buckets": BUCKETS, "hidden": 96, "max_len": max_len, "token_labels": TOKEN_LABELS, "punctuation": PUNCT, "structures": STRUCTURES, "speech": SPEECH, "emojis": EMOJIS, "selection": "dev_exact_then_token_accuracy", "best_epoch": best_epoch, "best_dev": best_dev, "test": test_metrics}))
    (args.out / "test.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in results))
    print(json.dumps({"test": test_metrics, "best_epoch": best_epoch, "best_dev": best_dev, "out": str(args.out)}))


if __name__ == "__main__": main()
