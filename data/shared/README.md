# Shared training-data workspace

This is the single repository-facing contract for all STT and formatter/LLM
experiments. Its contents are intentionally ignored except for these
instructions and directory markers: corpora, audio, raw transcripts, model
weights, private feedback, generated rows, caches, and run outputs must never
be committed.

| Lane | Purpose | Required companion record |
| --- | --- | --- |
| `stt/incoming/` | newly obtained audio/transcripts | source URL/version, license, consent/access terms, checksum |
| `stt/manifests/` | train/dev/test JSONL manifests | provenance ID, split method, transcript style, language/accent |
| `stt/benchmarks/` | held-out evaluation manifests | immutable benchmark/version and metric definition |
| `stt/feedback/` | opt-in, local feedback exports | collection consent and retention policy |
| `llm/incoming/` | licensed clean text or real-derived source rows | source/license and transformation history |
| `llm/review/` | human-review queues and decisions | reviewer protocol and approval state |
| `llm/prepared/` | validated trainer-ready JSONL | schema version, provenance IDs, data split, validator result |
| `llm/evaluations/` | held-out challenge suites | immutable suite version and critical-error rubric |

For every source, write a compact `provenance.json` beside it. At minimum:

```json
{
  "id": "source-YYYY-name-v1",
  "source_url": "https://…",
  "version": "…",
  "license": "…",
  "commercial_use": "unknown|allowed|restricted",
  "redistribution": "…",
  "languages": ["en-IN"],
  "kind": "human|corpus-derived|rule-derived|stt-derived|llm-synthetic",
  "created_at": "YYYY-MM-DD"
}
```

STT manifests must point to audio by path and carry only metadata the backend
actually produced. Formatter rows must retain raw STT, reference, target,
phenomenon labels, and provenance separately. Ambiguous formatter edits are
`KEEP` or excluded. See `docs/V6_DATASET_AUDIT.md` and
`docs/v6-dataset-schema.md` for the required semantic constraints.
