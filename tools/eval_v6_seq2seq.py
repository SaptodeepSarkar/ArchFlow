#!/usr/bin/env python3
"""Aggregate-only evaluation for a constrained V6 generative formatter."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
from v6_eval_aggregate import add_category_result, category_report
from eval_v6_linux_ct2 import model_sha256

PROTOCOL_DIR = Path(__file__).resolve().parents[1] / "training/cleanup-llm/scripts"
sys.path.insert(0, str(PROTOCOL_DIR))
from formatter_protocol import (  # noqa: E402
    IN_TAG, OUT_TAG, align_token_embeddings, initialize_v6_token_embeddings, max_new_tokens_v5,
    content_tokens as protocol_content_tokens, max_new_tokens_v6, prompt_v5, prompt_v6, v6_missing_protected_tokens,
    v6_missing_target_content_tokens, v6_preserves_source_order, v6_requires_copy_fallback,
    v6_unsupported_content_tokens,
)



def fields(row: dict) -> tuple[str, str]:
    if "utterance" in row:
        return row["utterance"]["raw_stt"], row["utterance"]["clean_target"]
    return row["source"], row["target_text"]


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).casefold()


def evaluation_code_sha256() -> str:
    """Hash the evaluator and its aggregate-reporting dependency together."""
    digest = hashlib.sha256()
    for path in (Path(__file__).resolve(), Path(__file__).with_name("v6_eval_aggregate.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--adapter", type=Path,
                        help="omit to evaluate the V5 base model with its production prompt")
    parser.add_argument("--protocol", choices=("v5", "v6"),
                        help="defaults to v6 when --adapter is set, otherwise v5")
    parser.add_argument("--data", type=Path, nargs="+", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int,
                        help="override the runtime-matched protocol output limit")
    parser.add_argument("--progress-interval", type=int, default=500,
                        help="print aggregate-only progress every N rows; 0 disables it")
    args = parser.parse_args()
    if args.progress_interval < 0:
        raise SystemExit("--progress-interval must be nonnegative")
    protocol = args.protocol or ("v6" if args.adapter else "v5")
    rows = []
    for data_path in args.data:
        rows.extend(json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines()
                    if line.strip())
    if not rows:
        raise SystemExit("evaluation input has no rows")
    tokenizer = AutoTokenizer.from_pretrained(args.adapter or args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    dtype = torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(args.model, torch_dtype=dtype)
    align_token_embeddings(model, tokenizer, force=(protocol == "v6"))
    if protocol == "v6":
        initialize_v6_token_embeddings(model, tokenizer)
    if protocol == "v6":
        if not args.adapter:
            raise SystemExit("V6 protocol requires a trained adapter")
        if tokenizer.convert_tokens_to_ids(IN_TAG) == tokenizer.unk_token_id or tokenizer.convert_tokens_to_ids(OUT_TAG) == tokenizer.unk_token_id:
            raise SystemExit("adapter tokenizer is missing the fixed V6 protocol tokens")
    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter)
    model = model.to("cuda" if torch.cuda.is_available() else "cpu")
    model.eval(); device = model.device
    exact = normalized_exact = 0
    novel_content_tokens = outputs_with_novel_content = 0
    raw_novel_content_tokens = raw_outputs_with_novel_content = copy_guard_fallbacks = 0
    raw_novel_numeric_tokens = raw_novel_word_tokens = 0
    raw_token_order_violations = 0
    raw_missing_protected_tokens = 0
    missing_target_content_tokens = 0
    outputs_missing_target_content = 0
    category_metrics: dict[str, dict[str, int]] = {}
    source_digest = hashlib.sha256()
    target_digest = hashlib.sha256()
    with torch.inference_mode():
        for row_index, row in enumerate(rows, 1):
            source, target = fields(row)
            source_digest.update(hashlib.sha256(source.encode("utf-8")).digest())
            target_digest.update(hashlib.sha256(target.encode("utf-8")).digest())
            prefix = prompt_v6(source) if protocol == "v6" else prompt_v5(source)
            encoded = tokenizer(prefix, return_tensors="pt").to(device)
            max_new = args.max_new_tokens or (
                max_new_tokens_v6(encoded["input_ids"].shape[1])
                if protocol == "v6" else max_new_tokens_v5(source)
            )
            generated = model.generate(**encoded, do_sample=False, max_new_tokens=max_new,
                                       pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id)
            output = tokenizer.decode(generated[0, encoded["input_ids"].shape[1]:], skip_special_tokens=True).strip()
            copy_guard_fallback = False
            raw_order_violation = False
            if protocol == "v6":
                raw_novel = (set(protocol_content_tokens(output))
                             - set(protocol_content_tokens(source)))
                raw_novel_content_tokens += len(raw_novel)
                raw_novel_numeric_tokens += sum(token.isdigit() for token in raw_novel)
                raw_novel_word_tokens += sum(not token.isdigit() for token in raw_novel)
                raw_outputs_with_novel_content += bool(raw_novel)
                raw_missing_protected_tokens += len(v6_missing_protected_tokens(source, output))
                raw_order_violation = not v6_preserves_source_order(source, output)
                raw_token_order_violations += raw_order_violation
                if v6_requires_copy_fallback(source, output):
                    output = source
                    copy_guard_fallbacks += 1
                    copy_guard_fallback = True
            exact += output == target
            normalized_exact += normalized(output) == normalized(target)
            missing_target = v6_missing_target_content_tokens(target, output)
            missing_target_content_tokens += len(missing_target)
            outputs_missing_target_content += bool(missing_target)
            novel = (v6_unsupported_content_tokens(source, output)
                     if protocol == "v6" else
                     set(protocol_content_tokens(output)) - set(protocol_content_tokens(source)))
            novel_content_tokens += len(novel)
            outputs_with_novel_content += bool(novel)
            add_category_result(
                category_metrics, row,
                exact=(output == target),
                normalized_exact=(normalized(output) == normalized(target)),
                copy_guard_fallback=copy_guard_fallback,
                novel_content_tokens=len(novel),
                missing_target_content_tokens=len(missing_target),
                token_order_violation=raw_order_violation,
            )
            if args.progress_interval and row_index % args.progress_interval == 0:
                print(json.dumps({"progress_rows": row_index, "total_rows": len(rows),
                                  "copy_guard_fallbacks": copy_guard_fallbacks,
                                  "novel_content_tokens": novel_content_tokens,
                                  "token_order_violations": raw_token_order_violations}),
                      file=sys.stderr, flush=True)
    report = {"schema_version": 2, "rows": len(rows),
              "source_set_sha256": source_digest.hexdigest(),
              "target_set_sha256": target_digest.hexdigest(),
              "base_model_sha256": model_sha256(args.model),
              "adapter_sha256": model_sha256(args.adapter) if args.adapter else None,
              "evaluation_code_sha256": evaluation_code_sha256(),
              "protocol_code_sha256": hashlib.sha256((PROTOCOL_DIR / "formatter_protocol.py").read_bytes()).hexdigest(),
              "exact_rate": exact / len(rows), "normalized_exact_rate": normalized_exact / len(rows),
              "novel_content_tokens": novel_content_tokens,
              "outputs_with_novel_content": outputs_with_novel_content,
              "raw_novel_content_tokens": raw_novel_content_tokens,
              "raw_novel_numeric_tokens": raw_novel_numeric_tokens,
              "raw_novel_word_tokens": raw_novel_word_tokens,
              "raw_outputs_with_novel_content": raw_outputs_with_novel_content,
              "copy_guard_fallbacks": copy_guard_fallbacks,
              "raw_missing_protected_tokens": raw_missing_protected_tokens,
              "raw_token_order_violations": raw_token_order_violations,
              "missing_target_content_tokens": missing_target_content_tokens,
              "outputs_missing_target_content": outputs_missing_target_content,
              "category_metrics": category_report(category_metrics),
              "protocol": protocol,
              "max_new_tokens_override": args.max_new_tokens,
              "runtime": "cuda" if torch.cuda.is_available() else "cpu"}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
