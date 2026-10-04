# STT synthetic vocabulary generation: canonical pipeline

The local CPU synthesis job continues in the original worktree. Its source
has not been changed mid-run. The reviewed generator, hash-only provenance
helper, audio validator, and tests are now included in the main integration
checkout so the next run does not depend on untracked local tooling.

Resume previously skipped any existing clip solely by ID and file existence.
The canonical generator additionally checks the target, audio checksum, model
checksum, voice-asset checksum, and speed before reuse. Mismatches stop with
an aggregate-only diagnostic and require a separate output pack. These checks
do not establish numerical equivalence between different inference providers.

Verification: eight tests pass across `tests.test_v6_vocab_resume`,
`tests.test_v6_synthetic_vocab_provenance`,
`tests.test_validate_v6_synthetic_vocab_audio`, and
`tests.test_split_v6_synthetic_vocab`.

The expanded pack is synthetic, not real Indian-English/Hinglish speech. After
generation stops, validate every clip and require the complete 79-term,
12-template, two-voice grid before creating training splits. Preserve the
previous seen-term heldout IDs using the splitter's `--freeze-heldout` option.
The pack is not itself evidence that STT is better than V5; protected-term,
real-speech WER, export, and Android hardware gates remain required.
