"""Exercise production prompt routing without loading weights or CUDA."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "training/cleanup-llm/scripts"
sys.path.insert(0, str(SCRIPTS))
from formatter_protocol import IN_TAG, OUT_TAG, prompt_v5, prompt_v6


class Encoding(dict):
    def __init__(self):
        super().__init__(input_ids=types.SimpleNamespace(shape=(1, 10)))
    def to(self, device):
        return self


class Tokenizer:
    unk_token_id = 0
    pad_token = "pad"
    def __init__(self, v6, output):
        self.v6, self.output, self.prompts = v6, output, []
    def convert_tokens_to_ids(self, token):
        return 1 if self.v6 and token in (IN_TAG, OUT_TAG) else 0
    def __call__(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return Encoding()
    def decode(self, tokens, **kwargs):
        return self.output


class Model:
    config = types.SimpleNamespace(use_cache=False)
    def to(self, device):
        return self
    def eval(self):
        pass
    def generate(self, **kwargs):
        return [[0] * 12]


class RuntimeTest(unittest.TestCase):
    def load(self, filename, tokenizer):
        model = Model()
        modules = {
            "torch": types.SimpleNamespace(bfloat16="bf16", no_grad=contextlib.nullcontext),
            "transformers": types.SimpleNamespace(
                AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *a, **k: tokenizer),
                AutoModelForCausalLM=types.SimpleNamespace(from_pretrained=lambda *a, **k: model)),
            "peft": types.SimpleNamespace(PeftModel=types.SimpleNamespace(
                from_pretrained=lambda *a, **k: model)),
        }
        spec = importlib.util.spec_from_file_location("runtime_under_test", SCRIPTS / filename)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, modules):
            spec.loader.exec_module(module)
        return module, modules

    def test_resident_uses_v6_protocol_and_copy_guard(self):
        source = "we should wait"
        for v6, output in ((True, "We should wait."), (True, "Launch a rocket."),
                           (False, "We should wait.")):
            tokenizer = Tokenizer(v6, output)
            module, modules = self.load("llm-server.py", tokenizer)
            stdout = io.StringIO()
            with patch.dict(sys.modules, modules), \
                 patch.object(module, "align_token_embeddings"), \
                 patch.object(module, "initialize_v6_token_embeddings"), \
                 patch.object(sys, "argv", ["llm-server.py", "/base", "/adapter"]), \
                 patch.object(sys, "stdin", io.StringIO(json.dumps({"id": 1, "text": source}) + "\n")), \
                 patch.object(sys, "stdout", stdout):
                module.main()
            result = json.loads(stdout.getvalue().splitlines()[-1])
            self.assertEqual(result["protocol"], "v6" if v6 else "v5")
            self.assertEqual(tokenizer.prompts, [prompt_v6(source) if v6 else prompt_v5(source)])
            self.assertEqual(result["text"], source if output == "Launch a rocket." else output)

    def test_one_shot_uses_the_same_v6_prompt_and_guard(self):
        source = "we should wait"
        for output in ("We should wait.", "Launch a rocket."):
            tokenizer = Tokenizer(True, output)
            module, _ = self.load("vaani_inject.py", tokenizer)
            result = module.clean(tokenizer, Model(), source)
            self.assertEqual(tokenizer.prompts, [prompt_v6(source)])
            self.assertEqual(result, source if output == "Launch a rocket." else output)
