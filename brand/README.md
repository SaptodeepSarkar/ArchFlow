# Vaani identity

**Your voice. Your words.** Vaani is an independent, local-first dictation app
for Linux and Android. The tone is personal, direct and honest about what the
software can do. Use concrete examples; avoid promises of perfect recognition,
meaning-changing rewrites, universal insertion or measured battery savings.

## Speakmark

The mark is a rounded V with a detached speech dot: a voice becoming a sentence.
Two shapes, no gradients or fine details. It should work at 16 px as well as on
an app launcher. The dot is a permanent part of the identity, not a recording
indicator. This is an original design, not a borrowed product mark.

`vaani-mark.svg` is the canonical app icon; `vaani-glyph.svg` is its transparent
variant. `assets/branding/vaani-mark.svg` and `website/assets/favicon.svg` mirror
the icon. Android vector resources reproduce the same geometry, with clear
space for adaptive masks. The GTK launcher/install paths use the canonical SVG.

## Palette

| Token | Hex | Use |
| --- | --- | --- |
| Paper | #FFFCF7 | Main surface |
| Ink | #243D4A | Text |
| Blue | #286D9F | Mark, primary controls, links |
| Sky | #DDEEFF | Selected states and supporting surfaces |
| Apricot | #FFCFAB | Warm illustration and secondary surfaces |
| Speech dot | #C8662C | Identity accent; not body text on apricot |
| Muted | #586B76 | Supporting text |
| Line | #D9E1E3 | Boundaries |

Use readable ink on light surfaces and white on blue controls. Keep apricot
supporting, and give status/error states text as well as color. No dark hero,
purple/plum palette, decorative gradients or perpetual fake recording animation.

The website uses system sans for navigation and Georgia for editorial headlines,
without external font requests. App controls use platform typography. The lowercase
`vaani.` wordmark is a website lockup; the product name remains **Vaani**.

`brand-kit.html` is a directly viewable reference. `../docs/design-tokens.json`
records the current palette. The website illustrations are explicitly examples,
not screenshots or performance evidence. Reduced motion and visible keyboard
focus are required.
