from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "training/cleanup-llm/scripts"))
from train_v6_seq2seq import (  # noqa: E402
    append_replay_rows, argument_parser, fingerprint_file, read_excluded_sources,
    read_rows,
)
from formatter_protocol import initialize_v6_token_embeddings  # noqa: E402


def edit_plan(source: str, target: str, origin: str = "generated-template") -> dict:
    tokens = source.split()
    return {
        "source": source,
        "target_text": target,
        "source_tokens": tokens,
        "token_labels": ["CAPITALIZE"] + ["KEEP"] * (len(tokens) - 1),
        "punctuation_after": {str(len(tokens) - 1): "PERIOD"},
        "structure": "PROSE",
        "speech_act": "STATEMENT",
        "emoji_intent": "NONE",
        "metadata": {"source": origin},
    }


class Seq2SeqDataTest(unittest.TestCase):
    def test_repeated_replay_flags_all_survive_argument_parsing(self) -> None:
        args = argument_parser().parse_args([
            "--train", "train.jsonl", "--dev", "dev.jsonl",
            "--replay", "hard-replay.jsonl", "--replay", "foundation.jsonl",
            "--model", "base", "--out", "candidate",
        ])
        self.assertEqual(args.replay, [Path("hard-replay.jsonl"), Path("foundation.jsonl")])

    def test_preflight_flag_parses_without_changing_training_defaults(self) -> None:
        args = argument_parser().parse_args([
            "--train", "train.jsonl", "--dev", "dev.jsonl",
            "--model", "base", "--out", "candidate", "--preflight-only",
            "--seed", "7",
        ])
        self.assertTrue(args.preflight_only)
        self.assertEqual(args.seed, 7)

    def test_replay_factor_is_reflected_in_admitted_row_counts(self) -> None:
        row = edit_plan("hello", "Hello.")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            counts = {}
            rows = []
            append_replay_rows(rows, path, counts, set(), replay_factor=3)
        self.assertEqual(rows, [{"source": "hello", "target": "Hello."}] * 3)
        self.assertEqual(counts["generated-template"], 3)

    def test_fingerprint_records_hash_and_size_but_not_payload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private-rows.jsonl"
            path.write_text('{"text":"not for the manifest"}\n', encoding="utf-8")
            result = fingerprint_file(path)
        self.assertEqual(result["bytes"], len('{"text":"not for the manifest"}\n'.encode()))
        self.assertEqual(len(result["sha256"]), 64)
        self.assertNotIn("not for the manifest", json.dumps(result))

    def test_automatically_validated_edit_plans_require_known_origin_and_exact_renderer(self) -> None:
        rows = [
            edit_plan("hello", "Hello."),
            edit_plan("hello", "Hello!", "generated-template"),
            edit_plan("hello", "Hello.", "unknown-source"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            counts = {}
            accepted = read_rows([path], counts)
        self.assertEqual(accepted, [{"source": "hello", "target": "Hello."}])
        self.assertEqual(counts["generated-template"], 1)
        self.assertEqual(counts["rejected_renderer_mismatch"], 1)
        self.assertEqual(counts["rejected_schema_or_provenance"], 1)

    def test_foundation_rows_require_approved_or_automated_status(self) -> None:
        rows = [
            {"annotation": {"review_status": "automated_validated"},
             "utterance": {"raw_stt": "hello", "clean_target": "Hello."}},
            {"annotation": {"review_status": "needs_human_review"},
             "utterance": {"raw_stt": "unsafe", "clean_target": "Unsafe."}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            counts = {}
            accepted = read_rows([path], counts)
        self.assertEqual(accepted, [{"source": "hello", "target": "Hello."}])
        self.assertEqual(counts["foundation_automated_validated"], 1)
        self.assertEqual(counts["rejected_schema_or_provenance"], 1)

    def test_real_derived_rows_are_counted_separately_from_foundation(self) -> None:
        row = {
            "source": {"type": "real_derived", "raw_stt": "spoken words"},
            "utterance": {"raw_stt": "spoken words", "clean_target": "Spoken words."},
            "annotation": {"review_status": "automated_validated"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "real.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            counts = {}
            accepted = read_rows([path], counts)
        self.assertEqual(accepted, [{"source": "spoken words", "target": "Spoken words."}])
        self.assertEqual(counts["real_derived_automated_validated"], 1)

    def test_frozen_sources_are_excluded_from_all_training_routes(self) -> None:
        training = [
            edit_plan("held out", "Held out."),
            {"annotation": {"review_status": "automated_validated"},
             "utterance": {"raw_stt": "also held out", "clean_target": "Also held out."}},
            edit_plan("keep this", "Keep this."),
        ]
        heldout = [edit_plan("held out", "Held out."),
                   edit_plan("also held out", "Also held out.")]
        with tempfile.TemporaryDirectory() as directory:
            train_path = Path(directory) / "train.jsonl"
            heldout_path = Path(directory) / "heldout.jsonl"
            train_path.write_text("".join(json.dumps(row) + "\n" for row in training), encoding="utf-8")
            heldout_path.write_text("".join(json.dumps(row) + "\n" for row in heldout), encoding="utf-8")
            counts = {}
            accepted = read_rows([train_path], counts, read_excluded_sources([heldout_path]))
        self.assertEqual(accepted, [{"source": "keep this", "target": "Keep this."}])
        self.assertEqual(counts["rejected_heldout_source"], 2)

    def test_untrained_protocol_embedding_rows_are_initialized_deterministically(self) -> None:
        class Tokenizer:
            unk_token_id = 99
            ids = {"<|v6_input|>": 4, "<|v6_output|>": 5,
                   "<|im_start|>": 1, "<|im_end|>": 2}

            def convert_tokens_to_ids(self, value):
                return self.ids[value]

        class Model:
            def __init__(self):
                self.embedding = torch.nn.Embedding.from_pretrained(
                    torch.arange(12, dtype=torch.float32).reshape(6, 2), freeze=False
                )

            def get_input_embeddings(self):
                return self.embedding

        model = Model()
        initialize_v6_token_embeddings(model, Tokenizer())
        self.assertTrue(torch.equal(model.embedding.weight[4], model.embedding.weight[1]))
        self.assertTrue(torch.equal(model.embedding.weight[5], model.embedding.weight[2]))


if __name__ == "__main__":
    unittest.main()
