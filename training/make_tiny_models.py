#!/usr/bin/env python3
"""Write tiny randomly-initialised Whisper and Qwen2 models for the CPU smoke.

Nothing is downloaded: the tokenizers are built here (a BPE with no merges for
Whisper, a word-level tokenizer with the Qwen chat template for the formatter),
so `smoke_test.sh` runs offline and cannot touch the 809M / 1.5B checkpoints.
"""

from __future__ import annotations

import argparse
import json
import os
import string

import torch
from tokenizers import Tokenizer, decoders, models, pre_tokenizers
from transformers import (
    PreTrainedTokenizerFast,
    Qwen2Config,
    Qwen2ForCausalLM,
    WhisperConfig,
    WhisperFeatureExtractor,
    WhisperForConditionalGeneration,
    WhisperProcessor,
    WhisperTokenizer,
)

LANGUAGES = ["en", "hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "ur", "as", "or", "ne", "si", "sd"]
SPECIAL = ["<|endoftext|>", "<|startoftranscript|>", "<|notimestamps|>", "<|startoflm|>",
           "<|startofprev|>", "<|nospeech|>", "<|translate|>", "<|transcribe|>"]
WORDS = ["the", "quick", "brown", "fox", "hello", "world", "so", "i", "think", "we",
         "should", "ship", "it", "a", "ok", "vaani"]
CHAT_TEMPLATE = (
    "{% for m in messages %}<|im_start|>{{ m['role'] }}\n{{ m['content'] }}<|im_end|>\n{% endfor %}"
    "{% if add_generation_prompt %}<|im_start|>assistant\n{% endif %}"
)


def make_whisper_tokenizer(directory):
    vocab = {}

    def add(token):
        if token not in vocab:
            vocab[token] = len(vocab)

    for token in SPECIAL:
        add(token)
    for i in range(1501):  # timestamp tokens <|0.00|> .. <|30.00|>
        add(f"<|{i * 0.02:.2f}|>")
    for language in LANGUAGES:
        add(f"<|{language}|>")
    for char in string.printable:
        if char.isprintable():
            add(char)
    for word in WORDS + ["th"]:
        add(word)
    # a valid merge needs both pieces and its result in the vocab
    open(os.path.join(directory, "merges.txt"), "w").write("#version: 0.2\nt h\n")
    json.dump(vocab, open(os.path.join(directory, "vocab.json"), "w"))
    tokenizer = WhisperTokenizer(vocab_file=os.path.join(directory, "vocab.json"),
                                 merges_file=os.path.join(directory, "merges.txt"))
    WhisperProcessor(feature_extractor=WhisperFeatureExtractor(), tokenizer=tokenizer).save_pretrained(directory)
    config = WhisperConfig(
        vocab_size=len(vocab), d_model=32, encoder_layers=10, decoder_layers=1,
        encoder_attention_heads=2, decoder_attention_heads=2,
        encoder_ffn_dim=64, decoder_ffn_dim=64, max_source_positions=1500,
        max_target_positions=64, pad_token_id=vocab["<|endoftext|>"],
        bos_token_id=vocab["<|startoftranscript|>"], eos_token_id=vocab["<|endoftext|>"],
        decoder_start_token_id=vocab["<|startoftranscript|>"],
        suppress_tokens=[], begin_suppress_tokens=[],
    )
    WhisperForConditionalGeneration(config).save_pretrained(directory)


def make_qwen_tokenizer(directory):
    tokens = ["<pad>", "<eos>", "<unk>"] + [c for c in string.printable if c.isprintable()]
    for word in WORDS + ["So", "I", "In", "another", "year", "maybe", "can", "help"]:
        if word not in tokens:
            tokens.append(word)
    vocab = {token: index for index, token in enumerate(tokens)}
    backend = Tokenizer(models.WordLevel(vocab=vocab, unk_token="<unk>"))
    backend.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    backend.decoder = decoders.ByteLevel()
    tokenizer = PreTrainedTokenizerFast(tokenizer_object=backend, eos_token="<eos>", pad_token="<eos>",
                                        unk_token="<unk>", chat_template=CHAT_TEMPLATE)
    tokenizer.save_pretrained(directory)
    config = Qwen2Config(
        vocab_size=len(vocab), hidden_size=32, intermediate_size=64, num_hidden_layers=2,
        num_attention_heads=2, num_key_value_heads=1, max_position_embeddings=1024,
        tie_word_embeddings=True, pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id,
    )
    Qwen2ForCausalLM(config).save_pretrained(directory)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    torch.manual_seed(17)
    for name, builder in (("stt", make_whisper_tokenizer), ("formatter", make_qwen_tokenizer)):
        directory = os.path.join(args.out, name)
        os.makedirs(directory, exist_ok=True)
        builder(directory)
        print(f"tiny model: {directory}", flush=True)


if __name__ == "__main__":
    main()
