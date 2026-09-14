# V5 post-base-training plan

This document covers only the STT and formatter LLM. TTS is not part of the
V5 training objective.

## Order

1. Finish base supervised training.
2. Evaluate the untouched base checkpoint on the fixed held-out sets.
3. Apply one technique at a time, keeping the same held-out rows untouched.
4. Compare every checkpoint against the base and the current V2/cozy control.
5. Promote only a checkpoint that improves recognition quality without breaking
   the mobile latency, memory, or safety limits.

## STT after base training

### 1. Supervised continuation

Continue from the best base checkpoint with confirmed references only. Use a
small learning rate, short 200–300-step experiments, gradient accumulation,
and checkpointing at 100-step intervals. Never train on the deterministic
held-out set.

### 2. Reward-guided sample weighting

Use the 1,000-clip feedback rewards and word-error metadata to weight examples:

- clean, high-reward examples keep normal weight;
- low-reward examples receive bounded extra weight;
- examples containing missing technical/proper terms receive bounded extra
  weight;
- weights are capped so noisy labels cannot dominate training.

This is sample weighting, not PPO or policy-gradient RLHF.

### 3. Acoustic augmentation

Apply randomized, low-intensity augmentation during training:

- gain variation;
- additive noise;
- speed perturbation;
- reverberation/short room impulse response;
- amplitude quantization and codec-like distortion.

The clean reference remains unchanged. Augmentation must not be applied to the
held-out benchmark.

### 4. Knowledge distillation

When a stronger teacher is available, train the student with a mixture of:

- confirmed-reference loss as the primary objective;
- teacher-token or teacher-logit loss as an auxiliary objective;
- optional feature/alignment loss when the architectures expose compatible
  representations.

The teacher is never allowed to replace a confirmed reference silently.

### 5. Hard-example mining

After each evaluation, collect substitutions, deletions, insertions, and
technical/proper-name failures. Deduplicate them, verify the reference, and
add only verified failures to the next training manifest. Re-evaluate on the
same fixed holdout after every continuation.

### 6. Vocabulary and context biasing

Keep personal vocabulary, application terms, filenames, acronyms, and technical
terms in a decoder/context layer or prompt bias list. Measure these separately
from general WER. Do not use an LLM to invent a replacement for an uncertain
content word.

### 7. CTC/RNNT path where supported

For a Zipformer/RNNT or CTC student, use the architecture's native objective
and compare it against the Whisper continuation. A CTC/RNNT run is useful only
if it beats the same held-out control at the target mobile size and latency.
Do not claim that an architecture is CTC/RNNT-trained when the actual model
does not support that objective.

### STT promotion gate

Record all of the following for base, V2/cozy, and each candidate:

- normalized overall WER;
- Indian-English subset WER;
- technical-term accuracy;
- proper-name accuracy;
- substitution, deletion, and insertion rates;
- CPU real-time factor and end-to-end latency;
- peak RAM and VRAM;
- model size and quantized model size.

V5 remains offline unless it improves WER and critical-term accuracy while
meeting the mobile resource budget. If it does not, retain the best control and
record the candidate as rejected.

## Formatter LLM after base training

### 1. Supervised fine-tuning

Train a small adapter on reviewed examples for punctuation, capitalization,
filler removal, false starts, backtracking, lists, emojis, intent labels,
technical-term preservation, snippets, replacements, and command-as-text
handling.

Use assistant-only loss masking and an explicit stop boundary. Keep content
grounded in the transcript and context.

### 2. Structured intermediate output

Prefer a constrained JSON/edit representation containing fields such as:

```json
{
  "operation": "format_only",
  "intent": "question",
  "text": "Can you open the browser?",
  "edits": [],
  "confidence": 0.94
}
```

The renderer, vocabulary replacement engine, snippet engine, and command safety
boundary remain deterministic. The formatter must not execute an instruction
merely because it appears in dictated text.

### 3. Groundedness and edit constraints

Score candidates for:

- preservation of transcript content;
- correct operation/intent;
- punctuation and structure;
- list and emoji decisions;
- technical/proper-term preservation;
- no unsupported additions or deletions.

Penalize unnecessary lexical edits and reject malformed, multi-object, or
action-like output at the runtime guard.

### 4. Preference optimization

Use DPO only after the SFT adapter produces reliably valid structured output.
Preferred/rejected pairs should specifically teach:

- preserve `CUDA`, `MCP`, `HTML`, names, and filenames;
- format a list without inventing items;
- keep a dictated command as text unless the user explicitly enters command
  mode;
- apply a requested snippet or replacement exactly;
- preserve negation and backtracking;
- add punctuation/emojis only when supported by the speech and context.

Do not run PPO without a validated scalar reward model and a safety evaluation.
For this narrow formatter, DPO is the first preference method; PPO is not a
default step.

### Formatter promotion gate

Use a fixed held-out contract set and require:

- valid schema output;
- exact operation/intent accuracy;
- grounded text;
- list/emoji/backtracking accuracy;
- technical-term preservation;
- zero unsafe execution decisions;
- acceptable CPU latency and memory after quantization.

Schema validity alone is insufficient. If a candidate improves style but loses
intent or changes content, keep the previous formatter.

## Integration order

1. Benchmark and select STT.
2. Benchmark and select the formatter.
3. Wire only passing candidates into Vaani.
4. Reload Vaani and run live tests.
5. Keep the previous model configuration available for immediate rollback.

No model weight, private recording, or audio cache belongs in Git.
