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
