# STT qualification failure is now a process failure

The aggregate STT comparer historically returned success after writing
`promotion_eligible: false`. That behavior is useful for collecting diagnostic
reports, but a qualification caller must not interpret it as a green gate.

Added `--require-promotion`, preserving report-only behavior for historical
diagnostic callers. The reserved Monsoon one-shot pipeline uses this flag.
It writes the immutable completion receipt for a completed rejected comparison
as well as for an accepted one, then exits with the gate result. A same-hash
revisit of a rejected receipt also fails; a different model remains refused.
Execution errors or missing comparison reports do not become completion
receipts. No Monsoon model evaluation was run for this change.

Fourteen comparison/qualification tests pass, including rejected report
retention with failure exit, accepted comparison success, mismatched controls,
and wrong V5 rejection before the public test is claimed. Shell syntax passes.
These unit tests do not constitute an end-to-end physical benchmark or prove
the future candidate's Indian-English performance.
