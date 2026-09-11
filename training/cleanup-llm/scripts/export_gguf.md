# Stage 8 (export): merged model → GGUF → Ollama

1. Merge the adapter back to a plain HF model (needs ~4 GB RAM, no GPU):

```bash
source env.sh
.venv/bin/python - <<'EOF'
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
base = "output/base-model"
tok = AutoTokenizer.from_pretrained(base, trust_remote_code=True)
m = PeftModel.from_pretrained(
    AutoModelForCausalLM.from_pretrained(base, trust_remote_code=True),
    "output/dpo-sft",  # or output/lora-sft to skip DPO
)
m = m.merge_and_unload()
m.save_pretrained("output/hf_merged")
tok.save_pretrained("output/hf_merged")
print("merged")
EOF
```

2. Convert to GGUF (needs llama.cpp):

```bash
git clone --depth 1 https://github.com/ggerganov/llama.cpp /tmp/llama.cpp
cmake -S /tmp/llama.cpp -B /tmp/llama.cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/llama.cpp/build -j --target llama-quantize
/tmp/llama.cpp/build/bin/llama-quantize --help >/dev/null  # sanity
python3 /tmp/llama.cpp/convert_hf_to_gguf.py output/hf_merged \
  --outfile output/vaani-cleanup-f16.gguf --outtype f16
/tmp/llama.cpp/build/bin/llama-quantize output/vaani-cleanup-f16.gguf \
  output/vaani-cleanup-q8.gguf Q8_0
```

3. Register with Ollama and wire Vaani:

```bash
printf 'FROM ./output/vaani-cleanup-q8.gguf\n' > output/Modelfile
ollama create vaani-cleanup:0.6b -f output/Modelfile
```

Then in Vaani:

```
cleanup.mode = "clean"
cleanup.endpoint = "http://localhost:11434"
VAANI_CLEAN_MODEL=vaani-cleanup:0.6b
```
