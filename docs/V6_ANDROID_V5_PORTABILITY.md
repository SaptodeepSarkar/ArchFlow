# Android V5 STT Portability Investigation

Status: host conversion/load/decode evidence only; no Android replacement or
hardware benchmark has been performed.

## Evidence found

The original fused Hugging Face checkpoint exists locally outside this Git
repository at Cozy’s `stt-finetune/output/hf_public_indian_v2/`. Its
`config.json` identifies `WhisperForConditionalGeneration`, `model_type`
`whisper`, 80 mel bins, and Whisper-small dimensions. The deployed Linux
artifact is separately a CTranslate2 int8 directory. Android currently loads a
whisper.cpp-compatible `ggml-base.bin` through `dev.ffmpegkit.whisper`.

Conversion must start from the fused Hugging Face checkpoint, never from the
CTranslate2 directory. The model is architecturally a normal Whisper checkpoint.
A host-side float conversion and one-slice load/decode sanity check has now
succeeded; that does not establish quality, timestamp parity, Android runtime
compatibility, or mobile resource fit.

## Reproducible bounded experiment

1. Use a clean whisper.cpp checkout with the fused HF checkpoint. Record the
   whisper.cpp commit, Transformers version, checkpoint checksum, and tokenizer
   files in a non-Git experiment ledger.
2. Use that checkout’s matching documented converter to create a float model.
   The checked whisper.cpp commit `a44e078` supplies
   `models/convert-h5-to-ggml.py`, which emits legacy `ggml`; it does not
   supply `convert-hf-to-gguf.py`. Do not use CT2 files as converter input.
3. Before quantizing, run a fixed license-cleared 100-clip slice through HF and
   whisper.cpp with the same language setting; retain hypotheses/timestamps and
   compute WER plus timestamp coverage. Abort on invalid tokens, material WER
   regression, or absent required metadata.
4. Install the candidate alongside—not over—Android base Whisper. On actual
   hardware measure peak PSS/RSS, RTF, end-of-utterance latency, WER, Hinglish
   behavior, and timestamp fields.
5. Replace Android base only if all six V6 gates in `AGENTS.md` are evidenced.

## Host-side result

On 2026-09-23, the fused checkpoint was converted with the documented
`convert-h5-to-ggml.py` path using only temporary compatibility tokenizer files
derived from its own `tokenizer.json`. The resulting float `ggml` model was
923 MiB and had SHA-256
`3a959f804218338f07e5b28091fbfc596f38353a6ea3ffe6449b76173f5406a2`.
The CPU `whisper-cli` built from the same `a44e078` checkout loaded the model
and decoded one fixed, license-cleared AMI pilot WAV. The checkpoint was never
converted from CT2 input.

## Reproduced f16 export (2026-09-26)

The earlier temporary artifact was not retained, so the export was reproduced
from the immutable fused checkpoint rather than reused by filename. The input
Safetensors SHA-256 was
`f81142acb8dcb81b2e24d02e8c2b7f2c1ab1303179a90a0e31e69c378f62be9a` and
the tokenizer JSON SHA-256 was
`7b469ff15eb7816315aa45eec391f5943d639b9d73d110f5c003df5192fd54e3`.
Its 50,258 ordinary-token vocabulary exactly matched the retained compatibility
`vocab.json`; special Whisper tokens came from the matching `added_tokens.json`.

The converter was whisper.cpp `a44e07845931421bb6f3447ce0010ed9dc76a118`.
It used only the checkpoint-derived tokenizer compatibility files and
`mel_filters.npz` from OpenAI Whisper
`86098128c0b4f24f0e2aa2994de830614b474227`. The resulting f16 legacy GGML
artifact is 487,601,984 bytes, SHA-256
`0300fec7628fed6c86e5a6cb1f500af0983a733dca55fff8437bdd34452b7f91`.
The CPU CLI built from that same whisper.cpp commit loaded and decoded a
five-second licensed AMI probe successfully; terminal recognition output was
discarded. This proves format/load/decode compatibility, not transcript
quality, numerical parity, timing parity, mobile RAM, latency, or Android ABI
compatibility.

This is a format/load/decode sanity check only. It does not provide a WER
comparison, timestamp-parity result, quantized artifact, Android installation,
or Android hardware measurement. Resource cap remains one 100-clip slice and
no training.
