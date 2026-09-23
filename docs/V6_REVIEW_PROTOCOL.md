# V6 Formatter Candidate Review Protocol

Use this protocol for `needs_human_review` rows only. Review is an annotation
step, not a request to improve factual content.

## Order

1. Start with `review_priority: "critical"` rows from
   `tools/triage_v6_review_candidates.py`. Those are flagged because the source
   reference and actual raw STT have lexical differences.
2. Read the raw STT as the model’s only runtime evidence. The reference helps
   identify an STT error but does not authorize V6 to replace a content word.
3. Set `REJECT` when a faithful target cannot be made without guessing missing
   content. Set `CORRECT` only when the target’s content is recoverable from
   the utterance itself. Use `ACCEPT` only when the proposed target is already
   faithful.
4. Preserve uncertainty, quoted fillers, deliberate repetition, reasoning,
   emotion, casual language, and swearing. Do not turn every `um`, `sorry`, or
   `actually` into a deletion.
5. Do not turn ordinary enumeration into a list. Approve structural output
   only where the utterance explicitly requests or dictates that structure.

## Required review record

Each non-pending decision needs `example_id`, `decision` (`ACCEPT`, `CORRECT`,
or `REJECT`), a non-empty human `reviewer`, and reviewer notes. `CORRECT` also
needs a non-empty `clean_target`. The supplied application tool rejects
ambiguous or duplicate decisions.

## Acceptance checks

- Every retained factual/content token is supported by raw STT or an explicit
  self-repair within the same utterance.
- No reference-only word is introduced solely to repair STT.
- Negation, quantities, technical tokens, URLs, paths, and quoted text survive
  unless the utterance clearly retracts them.
- Target edits are no more extensive than needed for faithfulness and requested
  formatting.
- The row remains in no split until review is applied and V6 validation passes.

## AMI pilot queue

`/tmp/vaani-v6-ami-pilot/combined-review-queue-triaged.jsonl` has 50 rows. Its
triage report flags 25 `reference_content_mismatch` rows as critical and leaves
25 without a lexical-risk flag. That flag is prioritization only—not approval.
