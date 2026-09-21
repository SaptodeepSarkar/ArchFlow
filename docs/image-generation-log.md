# Vaani onboarding image-generation log

Generated 2026-09-21 with Codex built-in image generation. The requested Adobe
connector did not establish a session, so no Adobe seed/variant metadata exists.
Generator-side seed metadata is unavailable. Each final was visually checked for
text, logos, UI, devices, green, and copied-reference features; none are present.

The review sheets use white rectangles as native onboarding wireframes: the top
rectangle is the real text-safe area and the bottom rectangle is the real CTA
safe area. The assets were additionally reviewed under a 75% `#0C1020` native
scrim (art visible at 25%): the outlined areas remain visually quiet enough for
cloud-white title/body/CTA content. The final app must still use a plain-colour
fallback and test contrast on-device.

| Output | Purpose | Selected candidate and final prompt summary | Source / reviewed output | Crop-safe zones | Approval reason |
|---|---|---|---|---|---|
| `01-arrival-voice-space.webp` | Welcome / “Get started” | Candidate 3: dim cobalt room implied through a translucent cloud-white curtain, small coral reflection, ink upper third | `source/01-arrival-voice-space.png`; `onboarding-image-reviews/01-arrival-review.png` | Top 0–35%; bottom 84–100% | Most open title field; intimate and human without a device, logo, or copied photo composition. |
| `02-keyboard-handoff.webp` | Keyboard enable | Candidate 2: left-lit frosted rounded planes at outer margins, calm central instruction space, coral rim glint | `source/02-keyboard-handoff.png`; `onboarding-image-reviews/02-keyboard-handoff-review.png` | Top 0–25%; centre 32–64%; bottom 84–100% | Strongest central copy reserve; it implies tactile rhythm without literal keys, letters, or a phone. |
| `03-ready-to-speak.webp` | Microphone readiness | Candidate 3: off-centre low sculptural translucent folds with cobalt/cloud light and pinpoint coral reflection | `source/03-ready-to-speak.png`; `onboarding-image-reviews/03-ready-to-speak-review.png` | Top 0–35%; bottom 84–100% | Conveys attention and breath without an orb, microphone, waveform, or generic AI imagery. |

All sources and WebP exports are 1440 × 2560 px (9:16). The generation prompts
used the directive’s required palette (`#0C1020` ink, `#526BFF` cobalt,
`#FFF7F1` cloud highlights, one restrained `#FF6B4A` signal) and explicit
exclusions for text, UI, logos, devices, green, Wispr Flow, robots, brains,
neural networks, soundwave logos, and gradient shortcuts. The full candidate
prompt set is preserved in the agent transcript; selected prompts are summarized
above to keep this repository log readable.
