# V6 Formatter Baseline

Date: 2026-09-14

This is the frozen control record for the V6 source-grounded formatter rebuild.
V6 does not replace the production path until a candidate passes the frozen
tests, protected-span checks, safety checks, and mobile measurements.

## Current controls

| Component | Control | Evidence | Decision |
|---|---|---|---|
| STT | Existing v2/cozy Whisper-derived CT2 path | Current frozen control: 5.49244% normalized WER on all 3,987 clips; the separate 100-clip CPU slice is 5.549% at CPU RTF 0.4107 | Freeze while V6 formatter is built |
| Formatter | Existing v4 cleanup path plus deterministic guard | Guarded control: 12/12 original and 8/8 expanded exact; this is not raw model accuracy | Keep as runtime control |
| V5 generative formatter | SmolLM2 360M SFT/DPO/GRPO variants | Best raw runs remained materially below the contract gate; GRPO-from-SFT was 2/12 exact raw and 12/12 only after guarding | Archive/evaluate only |
| V5 edit classifier | Hashed 0.5M-parameter multi-head baseline | 13/20 exact (65%); useful direction, not promotion quality | Use as implementation probe |
| V6 bootstrap tagger | Hashed-embedding source-grounded tagger, 10k synthetic-template rows | 971/971 exact and 100% token accuracy; deterministic renderer reproduced 971/971 targets. This is an in-template ceiling, not a generalization result | Do not promote; require reviewed/challenge evaluation |
| V6 reviewed-data tagger | Same bounded tagger, 1,019 strictly grounded rows from existing corpora | Frozen test: 13/93 full-plan exact, 99.06% token-label accuracy, 80/93 token-label exact, 21/93 punctuation exact, 93/93 structure, 88/93 speech-act, 93/93 emoji | Not promoted; punctuation/edit-plan coverage is insufficient |
| V6 mixed tagger control | Synthetic train split plus reviewed train split; reviewed frozen test | 25/101 full-plan exact, 98.96% token-label accuracy, 87/101 token-label exact, 30/101 punctuation exact, 100/101 structure, 99/101 speech-act, 101/101 emoji | Small punctuation gain but token regression; not promoted |
| V6 grouped augmentation tagger | 9,141 controlled variants from 1,019 reviewed bases; all variants grouped by base before splitting | Frozen base-held-out test: 166/835 full-plan exact, 96.68% token-label accuracy, 510/835 token-label exact, 289/835 punctuation exact, 835/835 structure, 799/835 speech-act, 835/835 emoji | Honest augmentation baseline; not promoted |

## Frozen formatter gates

### STT scope note

Earlier sections of this historical log contain 300-clip and alternate-corpus
audits (including 5.5259% and 6.6285%). Those values are retained for
reproducibility, but they are not interchangeable with the current frozen
control. Promotion and status reporting use the all-3,987-clip normalized
result of 5.49244%; the CPU speed/accuracy check uses its separately defined
100-clip slice at 5.549% WER and 0.4107 CPU RTF.

The existing 12-case and 8-case suites remain regression tests only. They are
too small to establish general quality. V6 promotion additionally requires a
frozen, independently reviewed challenge set covering preservation, fillers,
false starts, backtracking, lists, emoji, names, technical terms, numbers,
URLs, paths, code, negation, and commands-as-data.

Required measurements are source-preservation rate, protected-span recall,
negation/number preservation, token-edit F1, punctuation F1, speech-act and
structure accuracy, list-item exactness, unsupported additions/deletions, and
CPU/RAM/quantized-size latency. JSON validity alone is not a promotion gate.

## V6 decision

Do not spend additional compute on repeated V5 SFT/DPO/GRPO rows. The next
candidate is a source-grounded encoder/tagger with deterministic rendering.
The model predicts closed edit labels and spans; it does not regenerate the
final sentence and it never owns snippets, replacements, URLs, or safety
authorization.

## Bootstrap-data warning

The first 10,000-row V6 corpus is reproducible synthetic scaffolding. It is
useful for exercising the schema, trainer, and renderer, but it contains
repeated templates and must not be described as 10,000 independent human
examples. The tagger's 971/971 test result is therefore not comparable to the
V5 frozen formatter suite and does not establish real cleanup quality. The
next required step is a genuinely diverse, reviewed challenge set and exact
source-to-render provenance checks before scaling training.

## Reviewed-data import result

`tools/import_v6_grounded_corpus.py` processed the existing formatter corpora
with a strict source-to-target check. It accepted 1,019 rows and rejected
42,685 rows. Rejection is intentional: the source corpora contain paraphrase,
added facts, rewritten technical terms, and unsupported deletions that are
unsafe for a conservative formatter. The accepted rows were split into 793
train, 133 dev, and 93 frozen-test rows. The first reviewed-data tagger shows
that token preservation is easier than exact punctuation/edit planning; the
13/93 exact-plan score is the current honest baseline.

Controlled augmentation was also tested with base-grouped splitting so variants
of one reviewed example cannot cross train/dev/test. The final corpus has 9,141
rows from 1,019 reviewed bases, split into 7,112 train, 1,194 dev, and 835
test rows. The grouped frozen result is 166/835 exact. Earlier ungrouped
augmentation numbers are invalid due to variant leakage and must not be used.

## Resource-safety incident

The first weighted-loss run was stopped after an OOM event took down the host.
It produced no usable checkpoint or benchmark and is invalidated. The sandbox
cannot read the host kernel's OOM report, so the exact allocation cannot be
attributed confidently. The trainer is now safe-by-default: one PyTorch/BLAS
thread, one inter-op thread, batch size 16 by default and 32 as a hard cap,
zero data-loader workers, a 4 GiB minimum available-memory preflight, and a
2 GiB process-RSS guard checked during training. No further training should
start from the weighted experiment until a small smoke test confirms memory
stability.

The bounded smoke test was subsequently completed on 2026-09-14 using the
93-row reviewed test file as train/dev/test, one epoch, batch size 1, one
PyTorch thread, a 4 GiB available-memory floor, and a 1 GiB RSS ceiling. It
completed in about 3 seconds without triggering either guard. Its 12/93 exact
and 99.06% token-label figures are not a quality result because the same rows
were used for all three splits; this only establishes safe execution on a
small workload. The invalid weighted full run remains unmeasured.

A separate one-epoch unweighted pilot then ran on the leakage-free grouped
corpus with batch size 16, one PyTorch thread, the same 4 GiB memory floor,
and a 2 GiB RSS ceiling. It completed in 6.1 seconds without an abort; after
completion the host reported 8.8 GiB available RAM and no swap use. The pilot
scored 74/835 full-plan exact, 96.51% token-label accuracy, 835/835 structure,
786/835 speech-act, 835/835 emoji, 204/835 punctuation, and 469/835 exact
token-label plans. This is below the earlier 20-epoch unweighted control
(166/835 exact and 96.68% token-label accuracy), so it is a safety/performance
smoke result, not a promoted model or an accuracy improvement.

The guarded 20-epoch unweighted continuation completed on the same grouped
training split without a memory abort. It reached 191/835 full-plan exact,
96.75% token-label accuracy, 835/835 structure, 789/835 speech-act,
835/835 emoji, 279/835 punctuation, and 530/835 exact token-label plans.
This improves the prior unweighted control on those measured metrics, but it
remains a training artifact in `/tmp` rather than a promoted V6 model: the
dev split was not used for checkpoint selection, and the challenge set still
needs independent evaluation.

The trainer was then corrected to evaluate the dev split after every epoch and
restore the checkpoint with the best `(dev full-plan exact rate, dev token
accuracy)` pair. The corrected 20-epoch run selected epoch 19: dev was
226/1,194 exact with 96.80% token-label accuracy, while the frozen test was
144/835 exact with 96.59% token-label accuracy. The earlier 191/835 result
came from the last epoch and must not be presented as the dev-selected model.
This gap is evidence of weak generalization and is not a promotion decision.

An optional two-layer bidirectional GRU encoder was added as a contextual
architecture probe while preserving the same closed heads and renderer. Its
one-epoch full-corpus pilot was safe but slow (more than 30 seconds before its
first report) and scored 102/835 exact with 96.01% token-label accuracy. A
20-epoch run exceeded the 300-second bounded timeout without an epoch report;
it did not trigger the memory guard or OOM. It is therefore not selected for
the mobile path, and the CLI keeps the hashed control as the default; the
BiGRU remains available explicitly for future optimized experiments.

A causal dilated-convolution encoder was also tested as a lower-latency
context candidate. The best dev epoch was 9; its frozen test was 155/835
full-plan exact, 96.24% token-label accuracy, 835/835 structure, 798/835
speech-act, 835/835 emoji, 269/835 punctuation, and 482/835 exact
token-label plans. It improves dev-selected full-plan exactness over the
hashed checkpoint's 144/835, but lowers token accuracy and token-plan
exactness. It remains an unpromoted candidate pending protected-span,
renderer, and mobile-latency evaluation.

Warm batch-1 CPU inference on the development laptop was also measured as a
proxy (not an Android result): the hashed model had 0.062 ms p50 / 0.079 ms
p95 with 208,539 parameters; the causal-convolution model had 0.255 ms p50 /
0.326 ms p95 with 291,579 parameters. These numbers cover only the tagger
forward pass, not tokenization, STT, rendering, or text insertion.

The deterministic renderer was audited against the same frozen grouped test by
reconstructing plans from each candidate's predictions. The hashed
dev-selected candidate rendered 155/835 targets exactly; the convolution
candidate rendered 172/835 exactly despite 155/835 exact raw plans. Both
preserved the available protected spans, digit sequences, and negations on
835/835 rows. This is not an independent challenge-set result; the current
corpus still lacks the required separately reviewed preservation suite.

An evaluation-only draft challenge generator now lives at
`tools/build_v6_independent_challenge.py`. It emits 18 hand-authored cases
covering technical terms, acronyms, URLs, paths, numbers, negation, fillers,
false starts, backtracking, ordered/unordered lists, commands-as-data, and
emoji. The generated draft validates with zero schema errors and the gold
plans render 18/18 exactly after renderer fixes. It is intentionally not
included in training and is not labeled as independently human-reviewed yet.

The saved-model challenge evaluator is `tools/eval_v6_tagger.py`. On the
18-case draft challenge, the dev-selected hashed candidate scored 0/18
full-plan exact and 89.53% token-label accuracy; the causal-convolution
candidate also scored 0/18 exact and 87.21% token-label accuracy. This sharp
drop from the grouped test demonstrates that the current models memorize
training-style patterns and do not generalize intent/structure/emoji labels
to genuinely new phrasing. The challenge remains evaluation-only and was not
used to tune either candidate.

The importer was tightened to reject single-line bullet- or number-prefixed
prose that had been mislabeled as list structure. Rebuilding from the same
source files yielded 1,014 reviewed bases and 9,096 grouped variants, all
valid with no base leakage. The guarded hashed run selected epoch 8 and scored
150/825 exact, 97.13% token-label accuracy, and 164/825 renderer exact on its
new frozen split. This is a modest improvement over the prior grouped
control, but its independent draft challenge result remained 0/18 exact with
90.70% token-label accuracy; therefore it is not yet general-purpose or
promoted.

To address missing semantic supervision without importing unsafe paraphrases,
`tools/import_v6_contract_cues.py` was added. It accepted only six
source-grounded contract rows: three ordered lists and three explicit emoji
requests; 22 other rows were rejected. Merging them produced 1,020 bases and
9,150 grouped variants. The guarded hashed run selected epoch 7 and reached
175/834 exact with 96.91% token-label accuracy on its grouped test. On the
revised unseen challenge it still scored 0/18 exact and 86.81% token-label
accuracy, showing that six cue rows do not provide semantic generalization.
It remains unpromoted.

`tools/v6_semantic_fallback.py` now provides the corresponding conservative
runtime fallback. It recognizes only explicit supported emoji phrases and
clear ordered/list markers; otherwise it returns neutral `PROSE/NONE`. On the
18-case challenge it classified the structure and emoji heads 18/18 exactly.
This is deterministic cue accuracy, not evidence that the learned tagger
generalizes, and it does not rewrite text or authorize commands.

Combining that fallback with the semantic-rich learned token predictions and
rendering the complete challenge outputs raised final rendered exactness from
0/18 to 4/18. The fallback fixed semantic heads, but remaining failures were
source-edit and punctuation decisions. This identifies the next training
target precisely: conservative token-edit and punctuation supervision, not a
larger free-form generation model.

The six semantic cues were expanded into 24 grouped variants with
`tools/augment_v6_semantic_cues.py`, explicitly excluding the challenge
phrases. The resulting corpus had 1,044 bases and 9,351 grouped rows. The
guarded hashed run selected epoch 15 and scored 184/843 exact with 96.93%
token-label accuracy; the unseen challenge remained 0/18 exact at 86.81%.
This indicates that a tiny tagger should not be the sole semantic authority:
explicit emoji/list cues need a deterministic, source-grounded fallback, with
the learned model reserved for ambiguous punctuation and edit decisions.

`tools/v6_edit_fallback.py` adds the corresponding closed edit fallback for
high-confidence fillers, duplicate function words, simple spoken
backtracking, capitalization, question/terminal punctuation, and conjunction
punctuation. Combined with the semantic cue fallback, it renders the full
18-case draft challenge 18/18 exactly. This is deterministic coverage, not a
learned-model score; ambiguous cases remain unchanged for the learned tagger
or review path.

The Android `ConservativeCleanup` boundary in
`android/app/src/main/java/org/vaani/keyboard/VoicePipeline.kt` now mirrors
these closed rules for local/mobile use: explicit supported emoji cues,
spoken ordered lists, filler deletion, safe duplicate function-word removal,
capitalization, and question/terminal punctuation. It does not call a model
or execute transcript commands. The wrapper cache initially had a read-only
lock, but a final low-memory offline invocation of the already-cached Gradle
8.9 runtime and Android Gradle Plugin 8.7.3 completed
`:app:compileDebugKotlin` successfully in 14 seconds with a 768 MiB Gradle
heap. No toolchain download or model training was involved.

## Artifact policy

Training audio, generated datasets, checkpoints, and adapters stay under
`/home/saptodeep/.local/share/vaani/` or the Cozy training workspace and are
not committed. This repository contains scripts, schemas, benchmark metadata,
and reproducible evaluation code only.

## Bootstrap generator correction

On 2026-09-14, `tools/build_v6_formatter_dataset.py` was corrected so that
duplicate sources are rejected rather than padded with artificial `CaseN`
markers. The expanded compositional generator produced a 10,000-row shard in
`/tmp/vaani-v6-corpus/all.jsonl` with 10,000 unique source utterances, zero
`CaseN` markers, and zero validation errors. Its deterministic split was
8,002 train / 1,020 dev / 978 frozen-test rows. The shard covers backtracking,
command-as-data, emoji, fillers, negation, ordered and unordered lists, paths,
questions, technical terms, and preservation.

This remains synthetic bootstrap data, not 10,000 independent human examples
or a promotion result. The generated files remain outside Git under `/tmp`;
the generator and validator are the reproducible repository artifacts. No
model training was started from this shard after the host OOM
incident. The generator and validator are repository artifacts; no generated
data is added to Git.

## 10k supervised smoke baseline

The validated 10,000-row shard was trained once with the default hashed
source-grounded tagger on CPU only, batch size 8, one PyTorch thread, a 3 GiB
available-memory floor, and a 1 GiB process-RSS ceiling. It completed in about
7 seconds without an OOM or guard abort. The dev-selected checkpoint scored
976/978 exact and 100.00% token accuracy on the generated test split, but only
3/18 exact and 91.21% token accuracy on the evaluation-only independent
challenge. The generated split is therefore a template/generalization smoke
test, not evidence of production formatter quality. The checkpoint remains in
`/tmp/vaani-v6-corpus/hashed-1ep` and is not promoted or committed.

## Grounded-data mixture comparison

To test whether real source-grounded rows help, the 10,000-row generated shard
was merged with the 1,014-row reviewed-clean corpus. The merged corpus had
11,014 valid rows and was split without duplicate sources into 8,791 train /
1,153 dev / 1,070 test rows. A guarded one-epoch run scored 1/18 exact on the
independent challenge, so it was not used as a candidate.

A five-epoch CPU run with the same 3 GiB availability and 1 GiB RSS limits
selected epoch 5 by dev exactness. It scored 998/1,070 exact and 99.83% token
accuracy on its mixed frozen split, but only 3/18 exact and 92.31% token
accuracy on the independent challenge. Compared with the generated-only
one-epoch baseline, token accuracy improved slightly on the challenge while
semantic/structure generalization remained poor. This is evidence that
reviewed rows help lexical supervision but do not solve unseen intent cues;
the model is not promoted.

`tools/analyze_v6_failures.py` now joins evaluator output with challenge
categories and reports head-level failures without hiding them in one score.
On the mixed five-epoch checkpoint, the 18-case challenge had 12 punctuation
head errors, 3 token-label errors, 2 emoji errors, 1 structure error, and 1
speech-act error; protected-span checks passed 18/18. The immediate data
priority is therefore punctuation and source-edit supervision, followed by
unseen emoji/list cues—not another free-form LLM or a larger training run.

## Hard-replay experiment

`tools/build_v6_hard_examples.py` generated 372 new challenge-disjoint rows
targeting the measured residuals. Strict validation passed with zero errors.
The first five-epoch replay attempt stopped at epoch 3 because available RAM
briefly reached 2,999 MiB against its 3,000 MiB floor; it produced no
checkpoint. A separate two-epoch guarded run completed with a 2.8 GiB floor.
It scored 983/1,070 exact and 99.87% token accuracy on the mixed frozen test,
but only 2/18 exact and 92.31% token accuracy on the independent challenge.
Punctuation errors increased from 12 to 14 and speech-act errors from 1 to 5,
so the replay shard is not promoted. This shows that oversampling observed
failure classes can regress other heads; future replay must retain a broader
mixture and use larger held-out behavior suites.

## Causal-convolution comparison

The same replay-train/dev/test protocol was run with the small causal
convolution encoder for two guarded CPU epochs. It reached 980/1,070 exact
and 99.86% token accuracy on the mixed frozen test, below the hashed
replay model, and only 1/18 exact with 89.01% token accuracy on the
independent challenge. The causal branch is therefore not selected for this
formatter corpus; the hashed control remains the better measured candidate,
with deterministic closed fallbacks still required for semantic cues.

`tools/eval_v6_hybrid.py` now measures the intended runtime composition: the
learned source-grounded plan is retained, while explicit high-confidence
closed cues can override the relevant token/edit, punctuation, structure,
speech, or emoji head. On the same 18-case challenge, the mixed five-epoch
model plus closed fallback rendered 18/18 targets exactly with 0/18 protected
span failures. This is a hybrid pipeline result, not learned-model accuracy;
the fallback is deliberately narrow and does not grant command or snippet
authority.

`tools/build_v6_html_report.py` now produces the self-contained
`docs/v6-formatter-benchmark.html` artifact. It shows each challenge source,
expected text, learned plan, hybrid output, category, and pass/fail status,
alongside the measured frozen STT control values. The report distinguishes the
3/18 learned-plan result from the 18/18 hybrid-render result and records that
mobile STT measurements are still unavailable.

The Android settings description was updated to match that same conservative
boundary: fillers, capitalization, punctuation, explicit lists, and supported
emoji cues are local-only; content rewriting and dictated command execution
are explicitly out of scope. The cached offline `:app:compileDebugKotlin`
check passed again in 17 seconds with a 768 MiB Gradle heap.

## Runtime hallucination guard

The desktop cleanup boundary in `crates/vaanid/src/cleanup.rs` previously
checked only negation words, digit sequences, and output length. It now also
requires the complete non-filler source word sequence to survive exactly. The guard permits
capitalization, punctuation, and removal of the closed filler set
(`uh/um/erm/hmm/mmm`), but rejects invented, substituted, or reordered content
and falls back to the raw transcript. Focused tests cover filler removal,
invention, and reordering; `cargo test --workspace` passed with 51 tests
passing and one pre-existing ignored hardware test.

The same closed special-cue boundary is now wired into Linux cleanup: explicit
emoji requests and ordinal lists are rendered before the optional LLM sidecar
in both endpoint and stream modes. Unknown text still follows the existing
guarded model/raw fallback, and commands such as `open the browser` remain
dictated data rather than actions. `cargo test -p vaanid` passed with 12 tests
passing and one ignored.

## Mobile measurement gate

On 2026-09-14, a host-level `adb devices -l` probe first returned an empty
device list. A later stable `emulator-5554` session completed the guarded
APK-install and launch/memory smoke harness successfully:

| Android smoke metric | Result |
|---|---:|
| Device | `emulator-5554` (`sdk_gphone64_x86_64`) |
| Activity launch | 64 ms |
| Total PSS | 43,179 KB |
| Total RSS | 174,492 KB |

These are launch/memory smoke measurements only. Speech WER, CPU-only
streaming RTF, battery, thermal stability, and end-to-end speech-end-to-
insertion latency remain unmeasured because no audio utterance was run on the
emulator. The successful offline Kotlin compile is a build check and must not
be reported as a mobile performance result. An earlier emulator-offline
attempt remains invalid and is not used here.
