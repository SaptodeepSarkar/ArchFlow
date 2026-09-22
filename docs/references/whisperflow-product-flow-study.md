# Product-flow study: screens 4–23

This is a structural study of the reference screenshots in
`docs/screenshots/good-screens/`. It records sequence, hierarchy, and setup
logic only. Vaani must not reuse Wispr Flow names, copy, marks, illustrations,
app icons, or exact layouts. Use [the Vaani brand kit](../../brand/README.md)
for Vaani's colour, logo, typography, and component decisions.

## What the reference flow teaches

The reference does not begin by selling an account. It earns permission in a
specific order:

1. Make one useful promise about finished text.
2. Explain the interaction in increasingly concrete terms: concept, field,
   keyboard state, and completed result.
3. Let the person choose their language before asking the system to act.
4. Explain why each capability is needed immediately before its permission.
5. Make data and background-running choices understandable rather than hiding
   them in settings.
6. Ask optional discovery questions only after the value and trust case are
   clear.
7. Land in a calm utility product, where each tool has a focused empty state.

The strongest transferable device is **one real transition per screen**:
every screen has one headline, one explanatory object, and one decisive bottom
action. The sparse neutral surface makes the action and progress rail legible.

## Reference-to-Vaani map

| Reference | Interaction lesson | Vaani screen and original content |
| --- | --- | --- |
| 4 | State the finished benefit before settings. | **Clear words, wherever you write.** A lilac Vaani card shows spoken words becoming a clean sentence. |
| 5 | Introduce the product’s one interaction object. | **How Vaani works.** A single ribbon-V mark and three concise steps: hold, speak, release. |
| 6 | Show the interaction in an actual field. | **See it in a text box.** A Vaani-created message field and local control are illustrated, not a copied keyboard capture. |
| 7 | Ask language early, with an uncomplicated selector. | **Choose your writing language.** English, Hindi, and Bengali use tall outlined choice rows. |
| 8–9 | Rehearse the recording and completed states. | **Hold to speak / release to write.** A fictional message field changes from waveform to cleaned sentence. |
| 10 | Explain what disappears after the task. | **Vaani steps out of the way.** The compact voice control is shown as temporary, not a permanent chat bubble. |
| 11 | Reaffirm cross-app value. | **Write across your day.** A Vaani-specific abstract writing rail, not third-party app marks. |
| 12 | Show the destination product shell. | **Vaani workspace.** First-use home with Dictionary, Style, and Snippets tabs. |
| 13–14 | Ask for accessibility only after explaining the exact reason and limit. | **Find the field you chose.** Permission preparation then Android Accessibility settings launch. Copy explicitly says Vaani acts only on the focused editable field. |
| 15 | Put data sharing under an explicit choice. | **Keep your phrases private.** Local-only is selected by default; opt-in improvement is presented as optional. |
| 16 | Explain background readiness as a performance trade-off. | **Keep Vaani ready?** The person can allow readiness or skip; no hidden always-on listening claim. |
| 17 | Explain notification value before asking. | **Know if dictation needs you.** Notification permission remains optional. |
| 18–19 | Keep acquisition questions optional and late. | **How did you find Vaani?** A simple source list, then an optional drill-down. No account gate. |
| 20 | Make settings/navigation discoverable inside the product. | **Account drawer.** Local profile, privacy, feedback, and settings remain utility actions. |
| 21 | Give each tool a quiet empty state. | **Dictionary.** Search, scope chips, an empty-state sentence, and one add action. |
| 22 | Place a single featured feature inside a utility surface. | **Style.** An apricot feature panel and a compact current-style row. |
| 23 | Keep the next action obvious when empty. | **Snippets.** Search, empty-state copy, and one plum add button. |

## Vaani implementation sequence

The three completed dark splash pages remain the emotional opening. Their
primary action should continue into this sequence, with no mandatory login:

```text
Splash 1–3
  → promise
  → how it works
  → in-field rehearsal
  → language
  → hold/release rehearsal
  → temporary-control reassurance
  → accessibility explanation + Android hand-off
  → local-data choice
  → optional readiness / notifications / discovery
  → Vaani workspace
```

Sign-in belongs behind an explicit later sync action in Settings, never between
the opening promise and the first usable dictation path.

## Brand translation rules

- Use `Ink #19161C` for dark moments, `Paper #FDFBF8` for everyday screens,
  `Plum #6B3A85` for progress and selected state, `Lilac #E8DCFF` for the one
  primary action, and `Apricot #FFD4A3` for one supportive feature panel.
- Use the ribbon-V mark rather than an audio-wave copycat. The mark is a
  product identity, not a recording-state indicator.
- Use an editorial serif once in an explanatory screen; operational controls,
  choice rows, setup, and workspace use the sans face.
- Every permission screen must describe Vaani's actual Android behavior,
  including recovery/fallback. Do not imitate another product’s settings
  screenshots.
- Use a thin plum progress rail and broad lilac outlined CTA only for the
  current decisive action. Secondary actions are paper with an ink outline.

## Screenshot comparison rubric

When reviewing emulator captures, compare the Vaani implementation against
the reference at the level of hierarchy, not copied pixels:

1. One title and one visual explanation own the first screenful.
2. Primary action is full-width and anchored consistently at the bottom.
3. Paper surfaces retain generous intervals and fine dark boundaries.
4. Vaani's plum/lilac/apricot system and ribbon V are unmistakable.
5. Permission and keyboard claims match actual Android behavior.
6. The home tools read as calm utility surfaces, not stacked dashboard cards.
