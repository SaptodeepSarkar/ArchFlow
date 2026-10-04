# Frozen final formatter contrasts

A new 28-case agent-authored diagnostic suite was frozen while the
short-filler candidate was training, before evaluating its output. It covers
quoted and incidental fillers, repetition contrasts, explicit repair versus
narration, uncertainty/reasoning, requested versus unsolicited lists, list
termination, commands as text, emotion, code-switching, numbers, factual
claim preservation, pass-through, negation, and spoken acronyms.

Artifact outside Git:
`~/.local/share/vaani/v6-data/eval/final-contrasts-short-filler-20261004.jsonl`.
SHA-256: `23a8980450012170502f7aee7d56b240ff03af15d6b5976e5031f1edbcd1cc36`.
Bound training manifest SHA-256:
`82b674ad53b51f8275ba713499976168f5037c4ca09df0b6c2d097cc20c9573d`.

All 11 manifest input files were checked: zero normalized source overlap and
matching recorded input checksums. Normalization checks casing/punctuation
variants, not paraphrase or semantic/template independence. The suite is
synthetic and agent-authored, not independently human-reviewed ground truth
and not a substitute for diverse real-speech or Android hardware evidence.
Exact target matches alone should not arbitrate stylistic ambiguity.

The older challenge generator contains previously diagnosed examples and an
unsolicited-list target; do not describe it as untouched final evidence.
The new suite is evaluation-only. If its results inform another candidate,
it becomes diagnostic for that later candidate and a fresh final suite is
needed. No evaluation or promotion result is claimed here.

Three generator tests pass: unique labels/freeze, normalized-overlap rejection,
and changed-input rejection. Outputs cannot be overwritten.
