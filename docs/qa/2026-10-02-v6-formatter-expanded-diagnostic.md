# V6 formatter expanded diagnostic — 2026-10-02

This is an aggregate-only CPU rerun of the archived
`v6-formatter-smollm2-auto-real-v1-20260929` adapter against the current V5
base. It checks two newer suites with the current V6 copy guard and gold-target
content-deletion diagnostic. It is not a new training run or a release
qualification.

| Suite | Rows | V5 exact | Archived V6 exact | V6 delivered unsupported content | V6 missing gold content | V6 copy fallbacks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| spelling/meaning challenge v3 | 22 | 2 (9.09%) | 14 (63.64%) | 0 tokens / 0 outputs | 0 tokens / 0 outputs | 0 |
| contract-v5 hard-eval | 128 | 4 (3.125%) | 128 (100%) | 0 tokens / 0 outputs | 0 tokens / 0 outputs | 0 |

The challenge V6 raw generations contained three novel numeric tokens; none
reached delivered output. Its ordered-source digest is
`ff53e209cc9a438688a20f4876630b3e12d6744b400b3ff92a25cfb3786b7b97`.
The hard-eval ordered-source digest is
`541e1a9e369d698177d4fcce045c6918eae1c34f15a61818acd8001a099775f9`.

The 128 hard-eval rows have 128 unique source strings, all different from
their targets. An exact case-folded, whitespace-normalized source audit found
zero overlap with the archived adapter's documented training sources, dev
sources, or the earlier archived hard-eval set. This rules out direct source
reuse in those files; it does not rule out shared synthetic templates,
construction artifacts, or other forms of benchmark dependence. In
particular, the 100% result is surprising and must not be generalized to
natural speech.

The archived adapter remains unqualified. These two suites do not replace the
current retraining plan or its untouched mixed and real-derived held-out tests;
the archived run also predates the corrected contract-v5 data. Its known
18.45% fallback rate on the older mixed held-out test exceeds the current 5%
gate. Vaani therefore remains on V5 until a newly trained candidate passes
all current paired suites, including the current full mixed and real-derived
tests.

Reports are aggregate-only and are retained outside Git at
`~/.local/share/vaani/models/v6-formatter-v3-challenge-eval-20261002/`.
Evaluation runtime was CPU; it did not use the active STT training GPU.
