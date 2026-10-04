# Formatter evaluation slice reporting

The evaluator's category aggregator now includes foundation-schema `labels`
alongside `metadata.categories`. Real-derived test rows previously fell into
`uncategorized` despite carrying valid phenomenon labels. Aligned token edit
plans also produce aggregate source-length and edit-position slices, without
retaining source, target or generated text.

The evaluator fingerprint now includes both its own code and the aggregator.
V5/V6 comparisons must use matching evaluator versions; old report fingerprints
remain historical evidence, not directly interchangeable with the new version.
Ten aggregator/comparison tests pass, including label fallback, deduplication,
token-position slices and aggregate-only privacy checks.

Changes were prepared in a separate checkout. The active short-filler training
checkout and its recorded code hashes remain unchanged. Resume that candidate
from the same checkout and input/settings manifest. Once training is finished,
run the updated evaluator against both V5 and the final V6 adapter, writing
fresh report files rather than overwriting historical evaluations. These changes
improve diagnosis and provenance; they are not evidence of model improvement.
