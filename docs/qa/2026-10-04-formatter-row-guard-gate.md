# Formatter row-level guard coverage

The qualification gate previously compared raw missing-token counts and
raw order-violation counts with the total number of copy fallbacks. This
does not establish coverage on the same utterance. An unrelated fallback
could mask an unsafe row; conversely, one fallback protecting several
tokens could be incorrectly rejected.

The evaluator now emits schema 3 with
`unguarded_raw_violation_outputs`, counted before discarding each row.
The comparator requires that field and requires its value to be zero.
Historical reports without it must be re-evaluated, not inferred safe.
Only aggregate counts are retained; no transcripts or generated text are
added to reports.

Verification: `python -m unittest tests.test_compare_v6_seq2seq
tests.test_v6_eval_aggregate` passes 10 tests. Coverage includes an unsafe
row with an unrelated fallback and a guarded row missing multiple tokens.

These changes are in the evaluation checkout, not the checkpoint-frozen
training checkout. Final V5/V6 qualification must use matching fresh
reports from the updated evaluator. This is not evidence of model quality
or permission to promote either current candidate.
