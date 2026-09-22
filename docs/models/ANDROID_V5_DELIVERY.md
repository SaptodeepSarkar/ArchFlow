# Android V5 delivery boundary

The published [V5 reference-model release](https://github.com/SaptodeepSarkar/ArchFlow/releases/tag/v5.0.0-models)
contains the verified Linux/reference packages:

- Whisper V5 CTranslate2 int8 STT;
- SmolLM2-360M V5 formatter in Safetensors.

Neither reference artifact is an Android model payload. Android's embedded
runtimes load Whisper **GGML** and Llama **GGUF** respectively. The separate
[Android starter release](https://github.com/SaptodeepSarkar/ArchFlow/releases/tag/v5.0.0-android-starter)
therefore supplies a checksum-pinned Whisper Base GGML model (explicitly an
Android baseline, **not** V5 CT2 STT) and an Android Q8 GGUF export of the V5
formatter. The app downloads only the two direct runtime files in that catalog.
It is a safety property: the app must never download a file it cannot validate
and execute.

When Android-qualified exports are available, add them to
[`models/android-models.json`](../../models/android-models.json) with
`android_compatible: true`, a direct HTTPS asset URL, SHA-256 digest,
`size_bytes`, and `kind` of `stt` or `formatter`. The Android worker downloads
only those entries on a connected network, verifies the digest, and atomically
moves a completed asset into its private model directory. `size_bytes` is
shown in onboarding as an overall percentage, transferred bytes, and a live
ETA; it must match the uploaded release asset.

## Product flow

After the three splash screens, both sign-in and **Continue without an
account** enqueue the same connected-network model job. The rest of onboarding stays
available while it runs. Its final screen is a hard gate: it shows the active
model, exact overall percentage, downloaded/total bytes, and a rate-derived
ETA while it runs. The Vaani control is unavailable until both packages
verify, and Android posts a completion notification when they do. The overlay
service then draws a compact hold-to-dictate control only for a focused
editable, non-password field; it is removed again as soon as focus leaves that
field.

Never add audio, raw dictation, training data, user data, or an unverified
checkpoint to a model release.
