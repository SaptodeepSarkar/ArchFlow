# Vaani V6 Formatter — Clean-Rebuild Agent Directive

## Mission

Replace the current V5 generative cleanup-LLM training direction with a new, mobile-first formatter architecture based primarily on **source-grounded edit/tag prediction**, diverse training data, and deterministic rendering.

This is a clean research branch. Do **not** continue trying to rescue the old formatter by adding more SFT steps, repeated DPO pairs, more GRPO/RLVR iterations, or more compute on the same small corpus.

The STT is a separate subsystem. Do not destabilize the current STT while rebuilding the formatter.

---

## 0. Preserve the existing work, but leave it behind

Before changing anything:

1. Freeze the current V4/V5 formatter checkpoints, adapters, datasets, evaluation outputs, guards, scripts, and experiment logs.
2. Record the exact current best baseline metrics.
3. Move old formatter training artifacts into a clearly named archival/control area such as:

```text
archive/v5_formatter/
  checkpoints/
  adapters/
  datasets/
  dpo/
  grpo/
  evaluations/
  experiment_logs/
```

4. Do **not** delete historical work.
5. Do **not** use the old 37-row contract corpus as the primary V6 training corpus.
6. Do **not** expand the dataset by duplicating/repeating those rows.
7. Do **not** initialize V6 by blindly continuing the best V5 formatter adapter.
8. V5 may be evaluated as a control, but V6 training decisions must be based on the new data and architecture.

The previous work is evidence, not the foundation of the new corpus.

---

# 1. Freeze the STT baseline

The formatter rebuild must not become another STT experiment.

Keep the currently selected STT checkpoint/configuration frozen while developing V6.

Record:

- WER;
- substitution rate;
- deletion rate;
- insertion rate;
- technical-term accuracy;
- proper-name accuracy;
- CPU RTF;
- end-of-speech to final-ASR latency;
- model size;
- RAM usage.

Do not claim the earlier ~5.43% result as the stable baseline if it came from the smaller sample. Use the fair paired benchmark as the actual control.

V6 formatter training consumes STT-like text and must tolerate realistic STT mistakes, but it must not silently become an ASR correction model that invents words.

---

# 2. Abandon free-form sentence regeneration as the default task

The main V5 failure is architectural.

Do NOT make a small model solve all of these simultaneously by regenerating a new sentence:

```text
raw transcript
  -> understand semantics
  -> decide operation
  -> preserve every content word
  -> remove fillers
  -> resolve false starts
  -> resolve backtracking
  -> infer punctuation
  -> infer sentence type
  -> detect lists
  -> infer emoji
  -> preserve code/names/numbers
  -> generate JSON
  -> regenerate final text
```

This gives the model too much authority and creates lexical mutation.

V6 should instead use:

```text
STT transcript
      |
      v
source-grounded encoder/tagger
      |
      +--> token/span edit labels
      +--> punctuation labels
      +--> speech-act head
      +--> structure head
      +--> backtracking spans
      +--> optional emoji intent
      |
      v
deterministic validator
      |
      v
deterministic renderer
      |
      +--> user replacements
      +--> snippets
      +--> vocabulary aliases
      +--> safety policy
      |
      v
FINAL TEXT
```

The original STT token sequence remains the source of truth.

---

# 3. V6 model objective

First benchmark a small bidirectional encoder/tagging model in approximately the **30M–100M parameter range**.

Do not assume a 270M–360M decoder LLM is required.

The model should primarily predict transformations over source tokens/spans.

Example input:

```text
uh I need bread milk eggs and coffee
```

Possible token actions:

```text
uh      -> DELETE_FILLER
I       -> KEEP + CAPITALIZE
need    -> KEEP
bread   -> KEEP
milk    -> KEEP
eggs    -> KEEP
and     -> KEEP
coffee  -> KEEP + PERIOD_AFTER
```

Sentence-level heads could independently predict:

```text
speech_act = STATEMENT
structure  = PROSE
emoji      = NONE
```

For explicit list speech:

```text
first install cuda second run the tests third restart the app
```

the model should identify structure and source spans rather than generate three new strings from memory.

Possible output:

```text
structure = ORDERED_LIST

item_1_span = source tokens [...]
item_2_span = source tokens [...]
item_3_span = source tokens [...]
```

The renderer creates the final numbered list directly from source spans.

---

# 4. Separate prediction axes

Do not entangle all formatter behavior into one `operation` label.

Train/evaluate separate outputs where appropriate.

Recommended axes:

```text
token_edit:
  KEEP
  DELETE_FILLER
  DELETE_FALSE_START
  DELETE_RETRACTED
  CAPITALIZE
  NORMALIZE_ALLOWED

punctuation_after:
  NONE
  COMMA
  PERIOD
  QUESTION_MARK
  EXCLAMATION_MARK
  COLON
  SEMICOLON

speech_act:
  STATEMENT
  QUESTION
  EXCLAMATION
  FRAGMENT

structure:
  PROSE
  UNORDERED_LIST
  ORDERED_LIST

emoji_intent:
  NONE
  LAUGH
  THUMBS_UP
  CELEBRATION
  HEART
  OTHER_SUPPORTED

span_type:
  NORMAL
  PROTECTED
  CODE
  URL
  PATH
  NAME
  ACRONYM
  NUMBER
  TECHNICAL_TERM
```

Backtracking may need dedicated span/BIO tagging rather than a sentence-level label.

Do not force all heads into exactly this schema if experiments show a simpler representation is better. Preserve the principle: **closed, source-grounded decisions instead of unrestricted rewriting.**

---

# 5. Safety is not an LLM responsibility

Remove security-critical `needs_confirmation` decisions from the formatter model as the authoritative safety mechanism.

The model may emit useful semantic metadata, but deterministic code must decide whether dictated content requires confirmation or must remain data.

Examples:

```text
open the browser
delete the file
rm -rf /tmp
sudo pacman -Syu
```

These are dictated text unless the user explicitly entered a separate command/action mode.

The deterministic safety boundary owns:

- command-mode state;
- destructive-command detection;
- confirmation policy;
- tool/action authorization;
- URL validation;
- snippet expansion;
- replacement expansion.

Never permit a tiny formatter model to bypass these rules.

---

# 6. Build a NEW training corpus

The largest immediate bottleneck is information diversity.

Create a new V6 dataset containing **genuinely unique examples**, not repeated copies.

Initial target:

```text
10,000 unique examples -> first useful checkpoint
25,000 unique examples -> second checkpoint
50,000+ unique examples -> serious candidate
```

Do not block the project waiting for 50k. Train/evaluate progressively at 10k, 25k, and 50k to measure scaling.

Suggested initial distribution:

| Category | Approx. examples |
|---|---:|
| No-change / preservation | 8,000 |
| Punctuation / casing | 7,000 |
| Questions / exclamations | 4,000 |
| Fillers / disfluencies | 5,000 |
| False starts | 4,000 |
| Backtracking / self-correction | 6,000 |
| Unordered lists | 4,000 |
| Ordered lists | 4,000 |
| Names / proper nouns | 3,000 |
| Code / filenames / paths | 3,000 |
| Technical terminology | 3,000 |
| Numbers / dates / versions | 3,000 |
| Emoji requests | 2,000 |
| Indian-English / Hinglish-like constructions | 4,000+ |

These counts are starting targets, not fixed doctrine. Multi-label examples can belong to multiple categories.

Do not artificially balance the corpus so aggressively that it stops resembling real dictation. Maintain a large preservation/no-change population so the model learns that **doing nothing is often correct**.

---

# 7. Generate diversity, not paraphrase spam

Use a strong teacher model and programmatic generators to create candidate training rows.

The teacher is a data-generation tool, not ground truth.

Generate across:

- short and long utterances;
- informal and formal language;
- Indian English;
- American/British English variation where relevant;
- hesitations;
- repeated words;
- mid-sentence corrections;
- negations;
- multiple corrections in one utterance;
- lists with and without explicit ordinal markers;
- names from diverse linguistic backgrounds;
- programming terminology;
- Linux/Android/Git terminology;
- filenames and symbols;
- semantic version numbers;
- dates/times;
- URLs;
- paths;
- acronyms;
- commands dictated as literal text.

Create compositional examples.

Example:

```text
uh no wait deploy version five point three on tuesday actually make that wednesday and send my github
```

This combines filler removal, version preservation, backtracking, date replacement, and a snippet trigger.

The formatter must identify edits/structure while the deterministic snippet engine owns the actual GitHub URL.

---

# 8. Automatically validate generated training examples

Synthetic examples must pass deterministic validation before entering training.

Reject a generated sample if it:

- adds unsupported content;
- deletes protected content;
- changes negation unexpectedly;
- changes digits/version semantics unexpectedly;
- mutates a URL;
- mutates a file path;
- mutates source code;
- changes an acronym;
- invents a list item;
- drops a list item;
- generates a snippet value itself;
- converts dictated text into an executable action.

For every sample, maintain source-to-target provenance.

Prefer deriving final text mechanically from edit labels wherever possible.

If the edit program cannot reproduce the target exactly, the sample is invalid or needs human review.

---

# 9. Use human review strategically

Do NOT manually review every synthetic training example.

Human effort should concentrate on:

1. frozen evaluation sets;
2. difficult ambiguous examples;
3. samples rejected by validators;
4. model failure clusters;
5. a small random audit from every generated shard.

Build a high-quality human-reviewed dev/test corpus containing at minimum:

- ordinary dictation;
- Indian English;
- names;
- technical terms;
- code;
- URLs;
- paths;
- numbers;
- negation;
- fillers;
- false starts;
- backtracking;
- unordered lists;
- ordered lists;
- emojis;
- commands-as-data;
- compound cases.

The old 12/8-case suites may remain as regression/safety tests, but they are far too small to establish general formatter quality.

---

# 10. Evaluation split

Use three distinct data pools:

```text
TRAIN
  -> optimization only

DEV
  -> checkpoint selection
  -> hyperparameters
  -> threshold tuning
  -> architecture choices

FROZEN TEST
  -> final promotion decisions
```

Do not repeatedly tune against the frozen test set.

Also retain targeted challenge suites that report metrics by behavior instead of hiding everything inside one aggregate score.

---

# 11. Training sequence

Run experiments in this order.

## Phase A — dataset scaling

Train the edit/tag model with supervised learning only.

Evaluate:

```text
10k unique examples
25k unique examples
50k unique examples
```

Measure whether accuracy scales with genuinely new information.

Do not use DPO, GRPO, PPO, RLVR, or generic preference data during this phase.

## Phase B — architecture comparison

Compare at least:

```text
small encoder/tagger
vs.
existing 360M generative formatter control
```

Optionally test an intermediate/tiny generative or encoder-decoder architecture only if justified.

Compare:

- exact edit accuracy;
- token-edit F1;
- punctuation F1;
- structure accuracy;
- speech-act accuracy;
- backtracking accuracy;
- list exactness;
- protected-token preservation;
- unsupported addition rate;
- unsupported deletion rate;
- CPU latency;
- peak RAM;
- quantized size.

## Phase C — hard-example mining

After establishing a good supervised model:

1. evaluate it on DEV and challenge sets;
2. cluster failures by error class;
3. generate/collect **new unique examples** resembling those failure modes;
4. verify them;
5. mix them into the broad corpus;
6. retain substantial general-data replay;
7. retrain/fine-tune;
8. check for regressions.

Do not train solely on the model's last 30 mistakes.

## Phase D — preference/RL decision

Only consider DPO/RLVR if all of the following are true:

- supervised performance is already strong;
- there is a clear systematic residual behavior;
- the desired behavior cannot be expressed reliably as ordinary supervised labels/edit actions;
- preference pairs contain genuinely new information;
- reward components are validated against human judgment;
- a large enough evaluation set exists to detect regressions.

If those conditions are not met, do not run RL.

More RL is not inherently progress.

---

# 12. Do not repeat the previous failure pattern

Explicitly prohibit:

```text
37 examples
  -> more SFT steps
  -> duplicate rows
  -> DPO on repeated pairs
  -> GRPO
  -> more GRPO
  -> larger GPU
```

Backpropagation is not the current bottleneck.

SFT, DPO, and GRPO all ultimately perform gradient-based optimization. Better gradients on the same narrow information cannot manufacture missing task diversity.

The intended loop is:

```text
new information
      |
      v
better labels / edit structure
      |
      v
supervised learning
      |
      v
broad evaluation
      |
      v
failure analysis
      |
      v
new unique examples
      |
      +---------------> repeat
```

---

# 13. Protected spans

Implement source-grounded protection explicitly.

Examples:

```text
CUDA
HTML
MCP
CTC
Hyprland
Saptodeep
AudioProcessor.ts
calculateWER()
/home/user/project
/tmp/test
5.3.1
RTX 3050
https://example.com/a?x=1
```

A formatter should normally copy protected spans from source rather than regenerate them.

If normalization is allowed, implement a closed transformation with provenance.

Example:

```text
"version five point three"
    ->
NORMALIZE_NUMBER(source_span, "5.3")
```

The renderer performs/validates the conversion.

The model should not be free to substitute arbitrary numeric strings.

---

# 14. Snippets and replacements stay outside the model

Do not train:

```text
"my github" -> "https://github.com/user/repo"
```

inside model weights.

Instead:

```text
formatter:
  EXPAND_SNIPPET(github_primary)

deterministic snippet database:
  github_primary -> exact saved URL
```

Likewise:

```text
spoken alias:
  hyper land

canonical user vocabulary:
  Hyprland
```

belongs to the vocabulary/context/replacement system.

The model may identify a trigger/span when necessary. It does not own the replacement value.

This makes personalization instantaneous and avoids retraining.

---

# 15. Corrupt clean text to simulate realistic STT

The formatter must not train only on perfect written English.

Generate realistic STT-style inputs by applying controlled corruptions:

- punctuation removal;
- lowercase output;
- repeated words;
- fillers;
- false starts;
- homophone-like substitutions;
- spacing mistakes around technical terms;
- number words;
- fragmented sentences;
- missing casing;
- plausible proper-name mistakes.

However:

The formatter is not authorized to hallucinate a correction when the acoustic model is uncertain.

Where possible, future integration should provide:

```text
token confidence
N-best hypotheses
context vocabulary
protected spans
```

so lexical recovery can be grounded in ASR/context evidence.

---

# 16. Mobile-first promotion gates

Do not optimize only for accuracy.

Record on target CPU hardware:

- model load time;
- warm inference latency;
- p50 latency;
- p95 latency;
- p99 latency;
- peak RSS/RAM;
- quantized model size;
- CPU utilization;
- sustained behavior;
- total speech-end-to-final-text latency when integrated.

The formatter should be significantly faster than the user's perceived post-speech delay budget.

Quantize only after establishing a reliable FP baseline, then verify that quantization does not damage:

- backtracking;
- protected spans;
- punctuation;
- list structure;
- names;
- numbers.

---

# 17. Success criteria

A V6 formatter candidate should NOT be promoted merely because JSON/schema validity is high.

Promotion requires strong results on:

```text
source preservation
protected-span preservation
negation preservation
number preservation
punctuation
speech act
list structure
list item exactness
false-start removal
filler removal
backtracking
emoji intent
no unsupported additions
no unsupported deletions
commands remain data
mobile latency
memory
```

Any serious regression in names, numbers, negation, code, URLs, paths, or command/data boundaries is a blocker.

The deterministic guard stays enabled even after the ML model improves.

---

# 18. Required deliverables from this agent

Do not return only a proposal. Implement the new branch.

Produce:

1. an archive/control manifest for V5 formatter work;
2. the V6 dataset schema;
3. data generators;
4. automatic dataset validators;
5. train/dev/frozen-test split tooling;
6. the first 10k+ unique-example dataset;
7. a small encoder/tagger baseline;
8. supervised training scripts/configuration;
9. deterministic edit renderer;
10. evaluation tooling with per-category metrics;
11. benchmark comparison against the existing V4/V5 formatter control;
12. failure analysis;
13. a documented decision on whether to scale to 25k/50k or modify architecture.

Do not start preference optimization before delivering and evaluating the supervised V6 baseline.

---

# 19. Decision authority

You are authorized to modify implementation details if evidence shows that another source-grounded representation is better.

You are NOT authorized to quietly revert to unrestricted text regeneration simply because it is easier to implement.

When choosing between approaches, optimize in this order:

```text
1. semantic/lexical correctness
2. source groundedness
3. protected-term preservation
4. deterministic safety
5. formatter accuracy
6. mobile latency/memory
7. stylistic polish
```

Never trade factual/source preservation for prettier output.

---

# 20. First action

Before training anything:

1. inspect the current repository;
2. inventory V4/V5 formatter checkpoints, corpora, adapters, guards, training scripts, and evaluation scripts;
3. create the archive/control boundary;
4. identify components worth reusing only as infrastructure:
   - deterministic guard;
   - renderer utilities;
   - evaluation harness;
   - logging;
   - dataset loaders where compatible;
5. write a short `V6_BASELINE.md` recording the current formatter and STT controls;
6. define the V6 tag/edit schema;
7. generate and validate the first new dataset shard;
8. only then begin supervised training.

Do not spend additional compute on the old V5 formatter corpus unless explicitly requested for a controlled comparison.

The objective is not to make the old model finally pass.

**The objective is to build the correct formatter architecture.**
