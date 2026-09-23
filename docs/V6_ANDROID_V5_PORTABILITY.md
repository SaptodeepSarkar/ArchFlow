# Android V5 STT Portability Investigation

Status: research only; no Android replacement and no hardware benchmark has
been performed.

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

This is a format/load/decode sanity check only. It does not provide a WER
comparison, timestamp-parity result, quantized artifact, Android installation,
or Android hardware measurement. Resource cap remains one 100-clip slice and
no training.
