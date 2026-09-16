# Adding a model

Vaani model selection is data-driven. A model package must be discoverable and valid before it can be activated; UI code must not know model-specific filenames or runtime flags.

## 1. Export to a supported runtime

Choose a CPU-capable runtime supported by the target platform (currently whisper.cpp files or a CTranslate2 directory on Linux). Record tokenizer, language, quantization, license, and minimum memory. Keep weights outside Git.

## 2. Create a package

Place the package in the user model directory or a release artifact. Include a `model.json` manifest with `id`, `kind`, semantic `version`, languages, runtime, quantization, files, SHA-256 checksums, memory estimate, license, and capabilities. For an already exported local directory, use `tools/register-model-package.py`; it hashes named files and atomically creates the sidecar without copying weights.

## 3. Validate

Parse `model.json` through the shared manifest contract, then run the model validator. It must reject missing files, checksum mismatches, unsupported runtime/architecture, invalid metadata, and unsafe paths before loading anything. The portable parser/validator lives in `vaani-core`; the runtime supplies filesystem and hashing implementations.

## 4. Benchmark

Run the same fixture/benchmark manifest as the current model. Record WER, technical/proper-name accuracy, first partial/final latency, CPU RTF, peak RAM, model size, and backend label. Separate host CPU, GPU, emulator, and physical-device results.

## 5. Register locally

Install or copy the package into the user-local model directory, refresh discovery, and inspect diagnostics. Registration must not require editing Android UI, Linux overlay code, or Windows shell code.

## 6. Activate

Select the validated model in configuration. Activation is reversible and should retain the previous working model until the new model passes a load/health check.

## Compatibility rule

V5 is the current product generation. V6/V7 should add a package and benchmark result, not a new application architecture. Do not commit weights, audio, generated datasets, caches, or credentials.
