"""Regression test for Whisper's shared EOS/padding token ID."""
from __future__ import annotations

import sys
import itertools
import random
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock
import unittest
from pathlib import Path

try:
    import torch
    import peft  # noqa: F401
    import transformers  # noqa: F401
except ImportError:
    torch = None

if torch is not None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    from train_v5_whisper_lora import Collator, StreamingRows, WeightedTrainer
    from transformers import Seq2SeqTrainingArguments


@unittest.skipIf(torch is None, "optional Whisper training dependencies are unavailable")
class WhisperCollatorTests(unittest.TestCase):
    def test_custom_loss_accumulation_scaling_despite_forward_kwargs(self):
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.logits = torch.nn.Parameter(torch.tensor([1.0, 0.0]))

            @property
            def device(self):
                return self.logits.device

            def forward(self, labels=None, **kwargs):
                return SimpleNamespace(logits=self.logits.expand(labels.shape[0], labels.shape[1], 2))

        with tempfile.TemporaryDirectory() as directory:
            model = Model()
            trainer = WeightedTrainer(model=model, args=Seq2SeqTrainingArguments(
                output_dir=directory, use_cpu=True, report_to="none",
                gradient_accumulation_steps=8))
            self.assertFalse(trainer.model_accepts_loss_kwargs)
            trainer.current_gradient_accumulation_steps = 8
            trainer.accelerator.backward = Mock()
            inputs = {"labels": torch.tensor([[0, 1]]), "sample_weight": torch.tensor([1.0])}
            expected = trainer.compute_loss(model, dict(inputs)) / 8
            actual = trainer.training_step(model, dict(inputs), num_items_in_batch=16)
            self.assertAlmostEqual(actual.item(), expected.item(), places=6)
            self.assertAlmostEqual(trainer.accelerator.backward.call_args.args[0].item(),
                                   expected.item(), places=6)
            trainer.model_accepts_loss_kwargs = True
            unscaled = trainer.training_step(model, dict(inputs), num_items_in_batch=16)
            self.assertAlmostEqual(unscaled.item(), expected.item() * 8, places=6)

    def test_nonfinite_or_nonpositive_weights_fail_before_feature_padding(self):
        for weight in (float("nan"), float("inf"), 0, -1):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                Collator(None)([{"weight": weight}])

    def test_per_source_sampling_keeps_real_remainder_and_is_seeded(self):
        stream = StreamingRows(["real"], None, False,
                               auxiliary_source_rows=[["vocab"], ["other"]],
                               source_fractions=[0.2, 0.1])
        stream.encode_row = lambda row: row
        state = random.getstate()
        try:
            random.seed(42)
            draws = list(itertools.islice(iter(stream), 2000))
            random.seed(42)
            self.assertEqual(draws, list(itertools.islice(iter(stream), 2000)))
        finally:
            random.setstate(state)
        self.assertTrue(330 < draws.count("vocab") < 470)
        self.assertTrue(140 < draws.count("other") < 260)
        self.assertEqual(set(draws), {"real", "vocab", "other"})

    def test_real_eos_is_retained_and_only_batch_padding_is_masked(self):
        class FeatureExtractor:
            def pad(self, rows, return_tensors):
                return {"input_features": torch.zeros((len(rows), 1))}

        class Processor:
            feature_extractor = FeatureExtractor()

        batch = Collator(Processor())([
            {"input_features": [[0.0]], "labels": [7, 50257], "weight": 1.0},
            {"input_features": [[0.0]], "labels": [8, 9, 50257], "weight": 1.0},
        ])

        self.assertEqual(
            batch["labels"].tolist(),
            [[7, 50257, -100], [8, 9, 50257]],
        )


if __name__ == "__main__":
    unittest.main()
