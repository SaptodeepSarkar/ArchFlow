# Weighted Whisper loss and gradient accumulation

Inspection of installed Transformers 5.17.0 showed `training_step` divides
custom microbatch loss by accumulation steps only when the trainer does not
advertise accumulation-wide loss handling. Whisper and PEFT forward methods
accept `**kwargs`; that signature is insufficient evidence that our overridden
weighted loss uses `num_items_in_batch`. It does not use that argument.

`WeightedTrainer` now explicitly sets `model_accepts_loss_kwargs = False`.
The CPU regression executes the installed Trainer training step with eight
accumulations and a supplied token count. It checks that both returned loss
and the backward argument are the weighted microbatch mean divided by eight.
Restoring the old flag yields an eight-times-larger backward argument in the
same fixture. Four collator/sampling/loss tests pass without loading weights.

This matches the [official Trainer documentation](https://huggingface.co/docs/transformers/en/main_classes/trainer)
for custom losses that do not consume the accumulated item count. It is not
evidence that every historical run used this installed library or suffered
the same scale error. No historical model-quality score is reinterpreted.

The fix changes the next trainer recipe. Therefore a three-context control
must use the corrected loss before making a causal context-diversity claim
against the twelve-context candidate. Comparing only with the old rejected
20% candidate would conflate context diversity and loss scaling. Keep the
existing archived results for traceability, not as a matched new control.
The live formatter and synthesis jobs were not modified.
