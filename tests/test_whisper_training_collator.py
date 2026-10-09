"""Regression test for Whisper's shared EOS/padding token ID."""
from __future__ import annotations

import sys
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
    from train_v5_whisper_lora import Collator


@unittest.skipIf(torch is None, "optional Whisper training dependencies are unavailable")
class WhisperCollatorTests(unittest.TestCase):
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
