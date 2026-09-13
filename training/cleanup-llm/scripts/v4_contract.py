#!/usr/bin/env python3
"""Validation helpers for the v4 structured transcript contract."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

OPERATIONS = {"preserve", "punctuate", "grammar", "make_list", "numbered_list", "emoji", "format_only"}
FORBIDDEN_OPERATIONS = {"execute", "browse", "send", "open", "run", "delete", "install"}


@dataclass(frozen=True)
class Validation:
    valid: bool
    reason: str = ""


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def validate(record: object, source_text: str = "") -> Validation:
    if not isinstance(record, dict):
        return Validation(False, "record is not an object")
    required = {"operation", "result", "changed_spans", "needs_confirmation"}
    if set(record) != required:
        return Validation(False, "record keys do not match the contract")
    operation = record["operation"]
    if not isinstance(operation, str) or operation not in OPERATIONS:
        return Validation(False, "operation is not allowed")
    if any(word in operation.lower() for word in FORBIDDEN_OPERATIONS):
        return Validation(False, "action operation is forbidden")
    if not isinstance(record["result"], (str, dict)):
        return Validation(False, "result must be text or a list object")
    if not _strings(record["changed_spans"]):
        return Validation(False, "changed_spans must be a string array")
    if not isinstance(record["needs_confirmation"], bool):
        return Validation(False, "needs_confirmation must be boolean")
    if operation in {"make_list", "numbered_list"}:
        result = record["result"]
        if not isinstance(result, dict) or not _strings(result.get("items")):
            return Validation(False, "list result must contain string items")
    if source_text and operation in {"preserve", "format_only"}:
        # These operations may format but may not silently drop protected tokens.
        for token in re.findall(r"(?:https?://\S+|/[\w./-]+|\b[A-Z][A-Z0-9]{1,}\b|\b\d+(?:\.\d+)?\b)", source_text):
            if token.lower() not in str(record["result"]).lower():
                return Validation(False, f"protected token missing: {token}")
    return Validation(True)


def parse_and_validate(text: str, source_text: str = "") -> Validation:
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        return Validation(False, f"invalid JSON: {exc.msg}")
    return validate(record, source_text)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("record")
    parser.add_argument("--source", default="")
    args = parser.parse_args()
    result = parse_and_validate(args.record, args.source)
    print(json.dumps({"valid": result.valid, "reason": result.reason}))
    raise SystemExit(0 if result.valid else 1)
