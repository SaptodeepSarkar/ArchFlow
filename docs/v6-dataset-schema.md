# V6 Formatter Dataset Schema

The V6 foundation manifest is JSONL using schema `vaani.v6.formatter-example/2`.
One row represents one *current finalized utterance*. It is training evidence,
not an instruction and not an authorization to execute dictated content.

The earlier closed edit-plan schema remains useful as a baseline-control format,
but is insufficient for semantic repairs, STT provenance, or honest review
state. New V6 data must use this versioned schema.

```json
{
  "schema_version": "vaani.v6.formatter-example/2",
  "example_id": "v6-syn-000001",
  "source": {"name": "v6-foundation-seed", "record_id": "repair-001", "type": "synthetic"},
  "provenance": {"license_ref": "docs/V6_DATASET_AUDIT.md#synthetic", "transformation_history": ["hand-authored contrast pair"]},
  "utterance": {"raw_stt": "schedule it friday sorry monday", "reference_transcript": null, "clean_target": "Schedule it Monday."},
  "stt": {"backend": null, "model": null, "final": true, "words": []},
  "labels": ["explicit_repair", "contrast_positive", "meaning_preservation"],
  "language": {"primary": "en", "code_switching": false, "accent_or_domain": "synthetic"},
  "annotation": {"method": "hand-authored", "review_status": "needs_human_review", "reviewer": null},
  "split": null,
  "group_id": "repair-friday-monday",
  "audio": null
}
```

Required top-level keys are `schema_version`, `example_id`, `source`,
`provenance`, `utterance`, `stt`, `labels`, `language`, `annotation`, `split`,
`group_id`, and `audio`.

## Contract

- `source.type` is one of `real_derived`, `synthetic`, `corpus_derived`, or
  `manual`. Synthetic and real-derived data are never conflated.
- `utterance.raw_stt` is required. `reference_transcript` is required for
  `real_derived`; it may be null for hand-authored synthetic candidates.
- `clean_target` is required, non-empty formatted text. It must not introduce
  information unsupported by the utterance or explicitly marked repair.
- `stt.backend`, `stt.model`, and `stt.words` describe actual inference. They
  are null/empty only when inference has not happened. A word object has
  `text`, optional `word_start_ms`, `word_end_ms`, `pause_before_ms`,
  `pause_after_ms`, `segment_id`, `confidence`, and `alternatives`. Unknown
  values are `null`; they must never be invented.
- `audio` is either null or a portable relative reference plus checksum. Do
  not store absolute local paths in manifests.
- `labels` are open, documented phenomena labels. Include `ambiguous_keep` or
  exclude the row when deletion is not clearly justified.
- `review_status` is `needs_human_review`, `approved`, or `rejected`.
  An approved or rejected row must carry `annotation.method: "human-review"`,
  a non-empty `reviewer`, and non-empty `review_notes` explaining the named
  human decision. Only `approved` rows may enter a train/dev/test manifest.
- `group_id` binds contrast pairs, source sentences, template families, and
  known speakers. A group is assigned to exactly one split. For real speech,
  use a speaker-derived group when identity is available.
- `split` is `train`, `dev`, `test`, or null before review/splitting. The
  frozen 18-case challenge is evaluation-only and must never be represented in
  this manifest.

## Acceptance gates

The validator rejects malformed rows, absolute audio references, duplicate
IDs, non-final STT records, real-derived rows lacking reference or actual STT
identity, malformed timestamps, unsupported labels, and split/group leakage.
It also rejects high-similarity source variants placed in different groups via
a coarse-bucket token comparison, avoiding an O(n²) scan on a large corpus.
It reports candidates awaiting review and rejected rows. Semantic review is
mandatory: schema validity is not proof that a target preserves meaning.
