# V5 research upgrade: mobile ASR and a small formatter

This is the research-backed change to the V5 direction. The target is not a
general assistant. It is a local speech-to-text editor that preserves the
spoken content and emits a small, validated edit plan.

## Decisions

1. **Lock STT to the current V5 Whisper/CT2 model for refinement.** Do not
   restart with another architecture while the goal is token accuracy. The
   refinement loop is supervised continuation, verified hard-example replay,
   contextual vocabulary scoring, and teacher sequence distillation, with the
   existing CT2 model as the only promoted candidate.
2. Keep causal Zipformer/RNN-T as a documented future branch, not a competing
   active training direction. If activated later, use a CTC auxiliary loss,
   random streaming chunks, and sequence-level teacher transcripts. Do not
   compare teacher and student logits directly when their tokenizers differ.
3. Add a second-pass contextual rescoring experiment for names, developer
   terms, contacts, and user vocabulary. Measure target-term recall and false
   hotword insertion separately from WER.
4. Use ROVER or confidence-filtered agreement between strong teachers to make
   pseudo-labels. Keep verified hard examples in a bounded replay mixture so
   the model does not become over-specialized to technical speech.
5. Treat streaming UX as a first-class gate: first partial, stable-token,
   endpoint, finalization, p50/p95 latency, sustained RTF, RSS, and thermal
   behavior.

## Formatter model decision

The first small SmolLM2 experiments show that free-form generation is the
wrong interface: the guard can repair it, but the model itself has weak
operation selection. The next candidate is **FunctionGemma 270M**, fine-tuned
as a Vaani edit/function model, not as a chatbot. Its output should be a
function-like edit plan:

```json
{"op":"format_only","speech_act":"question","edits":[
  {"op":"INSERT_PUNCT","after":7,"value":"?"}
]}
```

The renderer, URL/snippet store, vocabulary replacement engine, emoji table,
and safety checks remain deterministic. The model never generates a saved URL
or executes a dictated command. For list and emoji cases it may select a
closed operation; the renderer supplies the exact source-grounded tokens.

Training order (do not abandon a candidate after base SFT):

1. SFT on reviewed edit plans, with positive and negative examples for
   questions, emotion, fillers, false starts, lists, acronyms, URLs, code,
   uncertainty, and commands-as-data.
2. Grammar/schema-constrained decoding and post-render validation.
3. Promote only if operation accuracy, groundedness, and protected-token
   recall pass the frozen suites.
4. Build a deterministic reward model from exact operation accuracy,
   groundedness, protected-token recall, and unsafe-action rejection.
5. Run DPO and ORPO on the same frozen preference pairs, keeping the better
   checkpoint.
6. Run PPO/RLVR only after the reward is calibrated against human-reviewed
   labels and only if DPO/ORPO plateau. Compare every checkpoint; never
   promote a method merely because it trained successfully.

## Experiments to run

| Experiment | Change | Promotion evidence |
|---|---|---|
| ASR-A | causal Zipformer/RNN-T, CTC auxiliary | WER, streaming p95, RSS |
| ASR-B | sequence-distilled labels from Whisper/Parakeet agreement | held-out WER improvement |
| ASR-C | context bias strength sweep | term recall vs false insertion |
| ASR-D | hard-example replay ratios | no regression on general Indian English |
| LLM-A | FunctionGemma 270M edit-plan SFT | exact operation + groundedness |
| LLM-B | smaller classifier/tagger baseline | compare latency and exactness |
| LLM-C | DPO only after A/B gate | held-out preference gain without mutation |

The current 5.492% CT2 result remains the baseline to beat. No candidate is
called mobile-ready until it has a physical-device measurement.

## Research basis

- Google’s mobile RNN-T work emphasizes streaming, long-tail vocabulary,
  user context, accented speech, and a second-pass rescoring stage.
- Google’s later streaming on-device work reports that distilling diverse
  non-streaming teachers into a streaming RNN-T can reduce the streaming gap.
- FunctionGemma is explicitly a 270M edge function-calling model with an
  official fine-tuning and on-device deployment path.
- Structured-output research supports grammar-constrained decoding, but also
  warns that complex constraints can reduce model confidence; therefore the
  schema must stay small and the renderer must own lexical preservation.
