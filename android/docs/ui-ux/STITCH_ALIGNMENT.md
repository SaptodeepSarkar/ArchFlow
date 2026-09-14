# Stitch alignment review — onboarding v3

Reviewed against Stitch project `5328162692191810137` and its `Editorial Tactile` design system on 2026-09-15.

## Decisions carried into Android

- Cold open uses the editorial line “Typing? / In this economy?” and a quiet local-pipeline meter. The former photo splash is not used in onboarding because it competed with the first decision and introduced a white-backed image block.
- The Stitch tone is treated as a starting point, not copied screen content. Vaani’s copy explains its actual IME lifecycle, offline recognizer boundary, permission timing, and no-auto-send behavior.
- The recurring mark is a pine-green `V` on the paper surface. `vaani_v.xml` has no tile or white rectangle; `vaani_mark.xml` remains the launcher/app icon with a green V.
- Paper is edge-to-edge and inset-aware. The onboarding ScrollView fills the viewport, so gesture/navigation areas do not become a second white canvas.
- The four Android states map to the Stitch narrative: cold open → microphone permission → Android keyboard paperwork → real dictation. The test field is retained when the IME reports success.
- Amber is interaction-only (cursor/focus/listening emphasis), never the logo.
- Step changes animate the narrative as one continuous handoff: outgoing copy/visuals ease left, the next state enters from the right, and the segmented rule advances with the state. The readiness pulse is a lightweight status signal; it is not fake microphone data.

## Deliberate native differences

Stitch uses Epilogue and Hanken Grotesk web fonts. This Android slice uses system sans-serif equivalents to avoid shipping an unapproved font payload; the display/body roles and scale remain aligned. OS permission and IME screens stay native because replacing them would make setup less trustworthy.

## Acceptance checks

- [ ] First page has no white image rectangle and the green V is the dominant visual anchor.
- [ ] Back/next preserve the current onboarding step.
- [ ] Returning from Android settings refreshes permission/IME status.
- [ ] Returning from the keyboard picker does not replace the focused test field.
- [ ] A successful first dictation changes only completion affordances; dictated text remains visible.
- [ ] Dark theme flips system-bar icon contrast as well as app surfaces.
