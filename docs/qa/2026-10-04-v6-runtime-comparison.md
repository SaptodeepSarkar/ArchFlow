# V6 formatter production-path runtime comparison

Date: 2026-10-04 20:00 IST
Code revision: `e55b53e2`
Status: completed diagnostic; not a promotion or release qualification.

The ignored Rust test `llm_sup::tests::v5_v6_paired_frozen_runtime_evaluation`
completed all three frozen fixtures through the production cleanup path and
semantic guard (`VAANI_RUNTIME_FULL_SUITES=1`). It compared the trained V5
adapter with the earlier V6 `smollm2-auto-real-v1` adapter, not the new adapter
currently training. The process reported `1 passed` in 5,076.75 seconds. Only
aggregate counts were emitted; no utterance text or model outputs were stored
in this report.

| Frozen suite | Rows | V5 exact target | V6 exact target | V5 sidecar accepted | V6 sidecar accepted |
|---|---:|---:|---:|---:|---:|
| Contract-heldout | 4,847 | 1,068 (22.0%) | 3,027 (62.5%) | 2,821 (58.2%) | 3,516 (72.5%) |
| Real-derived | 768 | 76 (9.9%) | 331 (43.1%) | 595 (77.5%) | 761 (99.1%) |
| Challenge | 22 | 6 (27.3%) | 13 (59.1%) | 16 (72.7%) | 16 (72.7%) |

`exact target` means output string exactly equaled the fixture target.
`sidecar accepted` means the production formatter route returned an accepted
sidecar result rather than another route; it is not itself a human semantic
fidelity score. This is encouraging evidence for the earlier adapter on these
fixtures, but does not establish generalization: the challenge suite is only 22
rows, the real-derived suite's provenance/coverage limits remain, and no
Android or live-dictation study is represented. The fresh 3,000-step candidate
must be evaluated separately against V5 and the frozen suites before any
promotion decision.

Artifact SHA-256:

- V5 `adapter_config.json`: `2e987118847d13cbc50d46d33f32a962c6ab9fb7f0091a7f1540e432388f87b2`
- V5 `adapter_model.safetensors`: `11657384ccd6ae54a9f45e03eb5d250bd223093d68dd9d1e4051742fe8fbb375`
- V6 `adapter_config.json`: `f2ef8fdeb5f2cf4f931e8c36a733c0b78b892f5a4de826182b3c2d17b8919e53`
- V6 `adapter_model.safetensors`: `da013f433133d03d4ef94f821e0093371a21880d441cf3912eb5a87390f6a1c9`
