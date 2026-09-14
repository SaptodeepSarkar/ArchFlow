# V6 Formatter Dataset Schema

The canonical V6 row is JSONL. Each row contains one source transcript and a
closed edit plan. `source_tokens` are the source of truth; the renderer must
be able to reproduce `target_text` from the source and the plan.

```json
{
  "id": "v6-000001",
  "source": "uh where is the MCP spec",
  "source_tokens": ["uh", "where", "is", "the", "MCP", "spec"],
  "token_labels": ["DELETE_FILLER", "KEEP", "KEEP", "KEEP", "KEEP", "KEEP"],
  "punctuation_after": {"5": "QUESTION_MARK"},
  "speech_act": "QUESTION",
  "structure": "PROSE",
  "emoji_intent": "NONE",
  "span_types": {"4": "ACRONYM"},
  "protected_spans": ["MCP"],
  "target_text": "Where is the MCP spec?",
  "metadata": {"categories": ["filler", "question", "technical"], "source": "reviewed"}
}
```

Allowed token labels are `KEEP`, `DELETE_FILLER`, `DELETE_FALSE_START`,
`DELETE_RETRACTED`, `CAPITALIZE`, and `NORMALIZE_ALLOWED`. Allowed punctuation
values are `NONE`, `COMMA`, `PERIOD`, `QUESTION_MARK`, `EXCLAMATION_MARK`,
`COLON`, and `SEMICOLON`. Structures are `PROSE`, `UNORDERED_LIST`, and
`ORDERED_LIST`. Emoji intents are closed: `NONE`, `LAUGH`, `THUMBS_UP`,
`CELEBRATION`, `HEART`, and `OTHER_SUPPORTED`.

`target_text` is a validation oracle, not a free-form generation target for
the model. Snippet values, replacements, URLs, and command authorization are
external deterministic operations and must not be embedded in model labels.
