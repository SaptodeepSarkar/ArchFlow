# Expanded STT vocabulary split safeguards

The synthetic vocabulary splitter now validates every source clip's target,
term hash, file existence and audio checksum before creating output files.
Previously it validated held-out clips only, leaving corrupt training audio
unchecked and an empty output directory after failure.

It also rejects duplicate or incomplete term/template/voice grids. Optional
expected dimensions reject missing whole terms or whole template/voice groups
that a relative grid check cannot detect. The expanded pack must be split with
`--expected-terms 79 --expected-templates 12 --expected-voices 2`, together with
`--strategy seen-term-context`. Keep term-disjoint evaluation separately for
unseen vocabulary; neither synthetic split establishes Indian-accent accuracy.

Verification: all three splitter tests pass. They check deterministic whole-term
separation, context holdout across both voices, missing/duplicate grid rejection,
and corrupted training-only audio failing before output creation. The currently
growing expanded manifest was rejected for containing only 43 of 79 planned
terms. The requested split output directory was verified absent afterward.

The CPU generator and GPU formatter training were both confirmed live during
this work. No STT training was started from the partial pack.

## Preserve earlier evaluations when expanding the grid

The context choice is a hash modulo the number of available templates. Expanding
from three to twelve templates can therefore put a previously evaluated context
into training. `--freeze-heldout PATH` now preserves every supplied context
across all voices (or the whole term under term-disjoint splitting). It rejects
frozen IDs absent from the input and does not change historical manifests.

For the next expanded seen-term-context experiment, supply the unchanged
`~/.local/share/vaani/models/v6-stt-vocab-20pct-20261002/vocab-split/heldout.jsonl`
along with the expected grid dimensions. This freezes its 158 evaluated clips
and any additional voice versions of their contexts. Train/eval row counts may
then differ from the nominal 22/2 per term and must be reported as actually
generated. The separate term-disjoint suite must retain its own frozen terms.

The regression test expands a complete three-frame pack to twelve frames and
verifies that all twenty original held-out IDs remain excluded from training.
This protects comparison validity; it does not establish an accuracy gain.
