# Corrected STT control: CPU preflight completed

The canonical V6 entry point now supports `--preflight-only`: hash inputs
without importing CUDA or starting training. Use a separate new output
directory; the subsequent training run must not overwrite the preflight.
Preflight does not validate acoustic decoding or optimize a model.

The corrected three-context control preflight completed successfully in a
1 GiB/no-swap scope with a ten-minute ceiling. It fingerprinted 22,761 unique
audio files, two manifests (AMI training plus the original 316-row vocabulary
training SQLite split), and eleven clean Whisper-small snapshot assets.
Output: `~/.local/share/vaani/models/v6-stt-corrected-control-preflight-20261004/`.
No GPU training or runtime promotion occurred.

Declared settings: pre-split streaming, no augmentation, 1,500 optimizer
steps, batch 2, accumulation 8, learning rate 1e-5, vocabulary source fraction
0.2 and vocabulary sample weight 8. These hashes identify the local inputs;
they do not independently prove source authenticity or license compliance.

Sampling audit used 24,000 nominal example draws, not 1,500 optimizer updates.
Expected vocabulary draws: 4,800; average expected draws per term: 60.76;
expected term exposure: approximately all 79, with no exposure warnings.
These are expectations, not realized training observations, and loss weighting
is separate from draw probability. Aggregate audit lives outside Git at
`~/.local/share/vaani/models/v6-stt-corrected-control-audit-20261004.json`.

Two identity/preflight tests pass, including a subprocess CPU preflight that
creates only its identity record and explicitly reports training not started.
A one-step CUDA smoke remains required after the formatter releases the GPU.
