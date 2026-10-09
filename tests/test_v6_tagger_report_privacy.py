#!/usr/bin/env python3
"""Check that V6 tagger evaluation returns metrics without example text."""
from __future__ import annotations

import unittest

import torch
from torch import nn

from tools.train_v6_edit_tagger import evaluate


class FixedOutputModel(nn.Module):
    def forward(self, feats, mask):
        batch, length, _ = feats.shape
        device = feats.device
        token = torch.zeros(batch, length, 6, device=device)
        punct = torch.zeros(batch, length, 7, device=device)
        structure = torch.zeros(batch, 3, device=device)
        speech = torch.zeros(batch, 5, device=device)
        emoji = torch.zeros(batch, 6, device=device)
        return token, punct, structure, speech, emoji


class TaggerReportPrivacyTest(unittest.TestCase):
    def test_evaluation_returns_aggregate_metrics_only(self) -> None:
        marker = "UNIQUE_PRIVATE_TRAINING_EXAMPLE"
        row = {
            "id": "test-id-1",
            "source": marker,
            "source_tokens": [marker],
            "token_labels": ["KEEP"],
            "punctuation_after": {},
            "structure": "PROSE",
            "speech_act": "STATEMENT",
            "emoji_intent": "NONE",
            "metadata": {"categories": ["privacy-test"]},
            "protected_spans": [],
        }
        results, metrics = evaluate(FixedOutputModel(), [row], 1, 1, 0, 4096, "privacy-test")
        self.assertEqual(metrics["rows"], 1)
        self.assertEqual(metrics["exact"], 1)
        self.assertNotIn(marker, repr((results, metrics)))
        self.assertNotIn("source", results[0])

    def test_real_derived_schema_uses_example_id_without_serializing_text(self) -> None:
        marker = "PRIVATE_REFERENCE_ALIGNED_TEXT"
        row = {
            "example_id": "v6-real-test-1",
            "source": {"name": "AMI", "type": "real_derived"},
            "utterance": {"raw_stt": marker, "clean_target": marker},
            "source_tokens": [marker],
            "token_labels": ["KEEP"],
            "punctuation_after": {},
            "structure": "PROSE",
            "speech_act": "STATEMENT",
            "emoji_intent": "NONE",
            "metadata": {"categories": ["real-derived-auto"]},
        }
        results, metrics = evaluate(FixedOutputModel(), [row], 1, 1, 0, 4096, "real-auto")
        self.assertEqual(metrics["rows"], 1)
        self.assertNotIn(marker, repr((results, metrics)))
        self.assertNotIn("source", results[0])


if __name__ == "__main__":
    unittest.main()
