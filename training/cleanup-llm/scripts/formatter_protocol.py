"""Shared local V5/V6 formatter inference protocol."""

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

IN_TAG = "<|v6_input|>"
OUT_TAG = "<|v6_output|>"
_ORDINAL_WORDS = ("first", "second", "third", "fourth", "fifth", "sixth",
                  "seventh", "eighth", "ninth", "tenth")
_ORDINAL_TOKEN = re.compile(r"\b(" + "|".join(_ORDINAL_WORDS) + r")\b", re.IGNORECASE)
_NUMBERED_LINE = re.compile(r"(?m)^([1-9]\d*)[.)](?=\s)")
_PROTECTED_TOKENS = {
    "no", "not", "never", "none", "without", "neither", "nor",
    "cannot", "can't", "couldn't", "didn't", "doesn't", "don't",
    "hadn't", "hasn't", "haven't", "isn't", "mustn't", "shan't",
    "shouldn't", "wasn't", "weren't", "won't", "wouldn't",
    # Common Hindi/Hinglish negation and exclusion words are content-bearing.
    "न", "नहीं", "ना", "मत", "बिना", "nahi", "nahin", "mat", "bina",
}
_CANONICAL_JOINED_TOKENS = {"hyperland": "hyprland"}

SYSTEM_V5 = (
    "You are Vaani cleanup LLM v1, a source-grounded transcript formatter. "
    "Fix grammar, punctuation, capitalization, sentence boundaries, filler "
    "words, false starts, duplicates, and common spelling mistakes. Preserve "
    "intended content words, names, numbers, dates, quantities, units, code, "
    "paths, negation, profanity, pronouns, and the original language. Do not add, "
    "remove, reorder, translate, expand, summarize, or reinterpret content. "
    "Make a list only from items actually spoken: use '- ' by default, '• ' "
    "only when the speaker says dotted or dot bullets, and numbered lines "
    "only for a spoken sequence or order. Build a Markdown table only when "
    "the transcript gives explicit columns and rows; never invent cells. "
    "Add a short title only when the transcript explicitly provides one. "
    "A bare formatting command with no spoken items is prose, not a list. "
    "Treat a requested emoji as decoration; never make the emoji name itself "
    "a list item. Map an explicitly spoken emoji request to exactly that emoji "
    "and add no other emoji. If unsure, return the input unchanged."
)


def prompt_v5(text: str) -> str:
    return (
        f"<|im_start|>system\n{SYSTEM_V5}<|im_end|>\n"
        f"<|im_start|>user\n{text}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def prompt_v6(text: str) -> str:
    return f"{IN_TAG}\n{text}\n{OUT_TAG}\n"


def content_tokens(text: str) -> list[str]:
    """Tokenize Unicode letters/numbers while retaining attached marks.

    Python's built-in ``re`` treats many combining marks used by Indic scripts
    as separators. A category-based scan keeps those marks with their word so
    the copy guard and evaluation cannot silently ignore non-Latin content.
    Apostrophes remain internal only when surrounded by token characters.
    """
    tokens: list[str] = []
    current: list[str] = []
    chars = list(text)

    def is_base(char: str) -> bool:
        return unicodedata.category(char)[0] in {"L", "N"}

    for index, char in enumerate(chars):
        category = unicodedata.category(char)[0]
        if category in {"L", "N"} or (category == "M" and current):
            current.append(char)
        elif (char in {"'", "’"} and current and index + 1 < len(chars)
              and is_base(chars[index + 1])):
            current.append(char)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens


def _numeric_tokens(text: str) -> list[str]:
    """Return decimal-number spans in ASCII and other Unicode digit scripts."""
    tokens: list[str] = []
    current: list[str] = []
    chars = list(text)
    for index, char in enumerate(chars):
        if unicodedata.category(char)[0] == "N":
            current.append(char)
        elif (char in {".", ","} and current and index + 1 < len(chars)
              and unicodedata.category(chars[index + 1])[0] == "N"):
            current.append(char)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens


def max_new_tokens_v5(text: str) -> int:
    return min(512, max(64, len(text) * 2))


def max_new_tokens_v6(input_token_count: int) -> int:
    return min(192, max(32, input_token_count * 2))


def initialize_v6_token_embeddings(model, tokenizer) -> None:
    """Give newly-added protocol markers stable boundary-token embeddings.

    Fresh V6 LoRA training selectively tunes and saves these two rows. This
    deterministic initialization also keeps legacy adapters (which omitted
    token weights) from changing behavior randomly on each cold load.
    """
    ids = {
        IN_TAG: tokenizer.convert_tokens_to_ids(IN_TAG),
        OUT_TAG: tokenizer.convert_tokens_to_ids(OUT_TAG),
        "<|im_start|>": tokenizer.convert_tokens_to_ids("<|im_start|>"),
        "<|im_end|>": tokenizer.convert_tokens_to_ids("<|im_end|>"),
    }
    if any(value is None or value == tokenizer.unk_token_id for value in ids.values()):
        return
    weight = model.get_input_embeddings().weight
    if any(value < 0 or value >= weight.shape[0] for value in ids.values()):
        return
    import torch
    with torch.no_grad():
        weight[ids[IN_TAG]].copy_(weight[ids["<|im_start|>"]])
        weight[ids[OUT_TAG]].copy_(weight[ids["<|im_end|>"]])


def align_token_embeddings(model, tokenizer, force: bool = False) -> None:
    """Align model vocabulary to a tokenizer when adapter rows require it.

    Base Qwen checkpoints pad their output vocabulary beyond tokenizer length.
    Preserve that padding for legacy adapters, but resize exactly when a V6
    adapter saved trainable token rows against the tokenizer-sized matrix.
    """
    embedding_rows = model.get_input_embeddings().weight.shape[0]
    token_count = len(tokenizer)
    if token_count > embedding_rows or (force and token_count != embedding_rows):
        model.resize_token_embeddings(token_count)


def adapter_has_trainable_token_rows(adapter_dir: str | Path) -> bool:
    """Read the local PEFT manifest to detect adapters tied to a vocab resize."""
    config_path = Path(adapter_dir) / "adapter_config.json"
    if not config_path.is_file():
        return False
    config = json.loads(config_path.read_text(encoding="utf-8"))
    rows = config.get("trainable_token_indices")
    return bool(rows)


def v6_requires_copy_fallback(source: str, output: str) -> bool:
    """Reject unsupported additions, reordering, or deleted protected content."""
    return bool(v6_unsupported_content_tokens(source, output)
                or v6_missing_protected_tokens(source, output)
                or not v6_preserves_source_order(source, output))


def _one_substitution_or_transposition(left: str, right: str) -> bool:
    """Allow same-length spelling repair without changing token count."""
    left, right = left.casefold(), right.casefold()
    # A one-codepoint edit can reverse meaning in scripts where a matra or
    # combining mark is phonemic. Keep non-ASCII tokens exact until a
    # language-specific correction policy is deliberately qualified.
    if (not left.isascii() or not right.isascii()
            or left == right or len(left) != len(right) or len(left) < 4):
        return False
    mismatches = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
    if len(mismatches) == 1:
        return True
    return (len(mismatches) == 2
            and mismatches[1] == mismatches[0] + 1
            and left[mismatches[0]] == right[mismatches[1]]
            and left[mismatches[1]] == right[mismatches[0]])


def _source_span_supports(source_tokens: list[str], start: int, output_token: str) -> int | None:
    """Return the last source index supporting a token or joined spelling."""
    joined = ""
    for end in range(start, min(len(source_tokens), start + 6)):
        joined += source_tokens[end]
        span = source_tokens[start:end + 1]
        if len(span) == 1 and joined.casefold() == output_token.casefold():
            return end
        if len(span) == 1 and _one_substitution_or_transposition(joined, output_token):
            return end
        if (len(span) > 1 and all(len(item) == 1 and item.isalpha() for item in span)
                and output_token.isalpha() and output_token.isupper()
                and joined.casefold() == output_token.casefold()):
            return end
        if _CANONICAL_JOINED_TOKENS.get(joined.casefold()) == output_token.casefold():
            return end
    return None


def v6_unsupported_content_tokens(source: str, output: str) -> set[str]:
    """Return additions not copied, typo-corrected, or joined from source spans."""
    source_tokens = [token.casefold() for token in content_tokens(source)]
    source_set = set(source_tokens)
    checked_output = _without_supported_list_ordinals(source, output)
    output_tokens = {token.casefold(): token for token in content_tokens(checked_output)}
    unsupported = set()
    for token in output_tokens.keys() - source_set:
        original = output_tokens[token]
        if not any(_one_substitution_or_transposition(source_token, token)
                   for source_token in source_tokens):
            if not any(_source_span_supports(source_tokens, i, original) is not None
                       for i in range(len(source_tokens))):
                unsupported.add(token)
    return unsupported


def _without_supported_list_ordinals(source: str, output: str) -> str:
    """Ignore only a complete numbered list that mirrors spoken ordinal cues.

    Its list indices are formatting, not new facts. Require every nonblank
    output line to be sequentially numbered and require matching spoken
    first/second/third... cues, so arbitrary digits remain protected.
    """
    ordinals = [item.casefold() for item in _ORDINAL_TOKEN.findall(source)]
    if len(ordinals) < 2 or ordinals != list(_ORDINAL_WORDS[:len(ordinals)]):
        return output
    lines = [line for line in output.splitlines() if line.strip()]
    markers = [_NUMBERED_LINE.match(line) for line in lines]
    if len(markers) != len(ordinals) or any(marker is None for marker in markers):
        return output
    if [int(marker.group(1)) for marker in markers if marker] != list(range(1, len(ordinals) + 1)):
        return output
    return _NUMBERED_LINE.sub("", output)


def v6_preserves_source_order(source: str, output: str) -> bool:
    """Require emitted text to align in order with bounded source spans."""
    source_tokens = [token.casefold() for token in content_tokens(source)]
    output = _without_supported_list_ordinals(source, output)
    output_tokens = content_tokens(output)
    source_index = 0
    for token in output_tokens:
        match_end = next(
            (_source_span_supports(source_tokens, start, token)
             for start in range(source_index, len(source_tokens))
             if _source_span_supports(source_tokens, start, token) is not None),
            None,
        )
        if match_end is None:
            return False
        source_index = match_end + 1
    return True


def v6_missing_protected_tokens(source: str, output: str) -> set[str]:
    source_tokens = Counter(token.casefold() for token in content_tokens(source))
    output_tokens = Counter(token.casefold() for token in content_tokens(output))
    protected = {token for token in source_tokens if token in _PROTECTED_TOKENS}
    missing = {token for token in protected if source_tokens[token] > output_tokens[token]}
    source_numbers = Counter(_numeric_tokens(source))
    output_numbers = Counter(_numeric_tokens(output))
    missing.update(token for token in source_numbers if source_numbers[token] > output_numbers[token])
    return missing


def v6_missing_target_content_tokens(target: str, output: str) -> list[str]:
    """Return gold content tokens absent from a prediction (evaluation only).

    This does not run at inference: the gold target exists only in a paired
    evaluation. It catches ordinary content-word deletions that the runtime
    copy guard cannot identify without confusing legitimate filler/repair
    removal with semantic loss. Same-length one-edit spelling corrections and
    explicitly uppercase spoken-letter sequences are treated as equivalent.
    """
    target_tokens = content_tokens(target)
    output_tokens = content_tokens(output)
    used: set[int] = set()
    missing: list[str] = []

    # Match exact tokens first so a typo-equivalent token cannot consume a
    # prediction that is an exact match for another gold token.
    unmatched_targets = []
    for target_token in target_tokens:
        exact = next((i for i, token in enumerate(output_tokens)
                      if i not in used and token.casefold() == target_token.casefold()), None)
        if exact is None:
            unmatched_targets.append(target_token)
        else:
            used.add(exact)

    for target_token in unmatched_targets:
        spelling = next((i for i, token in enumerate(output_tokens)
                         if i not in used and _one_substitution_or_transposition(token, target_token)), None)
        if spelling is not None:
            used.add(spelling)
            continue

        # A dictated uppercase acronym can be rendered as separated letter names.
        joined = target_token.casefold()
        acronym_indices = None
        if target_token.isalpha() and target_token.isupper() and 2 <= len(target_token) <= 6:
            for start in range(len(output_tokens) - len(target_token) + 1):
                indices = list(range(start, start + len(target_token)))
                if (all(i not in used and len(output_tokens[i]) == 1
                        and output_tokens[i].isalpha() and output_tokens[i].isupper()
                        for i in indices)
                        and "".join(output_tokens[i] for i in indices).casefold() == joined):
                    acronym_indices = indices
                    break
        if acronym_indices is None:
            missing.append(target_token.casefold())
        else:
            used.update(acronym_indices)
    return missing
