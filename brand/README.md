# Vaani brand kit

[`brand-kit.html`](brand-kit.html) is the canonical visual reference for Vaani.
Open it directly in a browser; it has no framework, build step, web fonts, or
runtime dependency. It is a design specification, not production UI.

## What belongs where

| Part | Use it for | Do not use it for |
|---|---|---|
| Ribbon V mark | App icon, launcher, compact system surface | Recording state, waveform, or arbitrary recolours |
| Paper / ink | Everyday app surfaces and readable text | A decorative dark theme everywhere |
| Plum | Progress, selected controls, intentional moments | Large default app backgrounds |
| Lilac outlined CTA | One decisive onboarding or permission action | Multiple competing actions on a screen |
| Apricot | A featured benefit or small warm supporting moment | Error, warning, or success meaning |
| Serif display | One onboarding/feature headline | Settings, lists, fields, navigation, or overlay text |
| Manrope sans | All operational UI: labels, controls, settings, overlay | Mixing several sans families |

## Sections in the kit

1. **Identity** — source SVG and approved app-mark/lockup contexts.
2. **Colour** — named colour values and their semantic role.
3. **Type** — editorial display use versus operational sans use.
4. **Actions** — primary, secondary, dark, and text-only button hierarchy.
5. **Selection** — tall outlined option rows and selected state.
6. **Voice box** — the small, non-focus-stealing dictation overlay.
7. **Tokens** — names that should be retained in implementation code.

## Implementation guidance

Treat the CSS custom properties at the top of `brand-kit.html` as the design
source of truth. Mirror their *semantic names*, rather than copying raw hex
values around the codebase:

```text
color.brand.plum
color.action.lilac
radius.action
stroke.control
```

Android Compose, QML, and any future React client should create platform-native
components from those tokens. The HTML demonstrates hierarchy and behaviour; it
does not prescribe fixed pixels over platform accessibility, touch-target, font
fallback, or reduced-motion requirements.

The source app icon is [`../assets/branding/vaani-mark.svg`](../assets/branding/vaani-mark.svg).
Do not redraw it in code. Export platform-sized raster assets from the SVG when
a platform requires them, retaining the rounded-square silhouette and clear
space.

## Product constraints

The brand must remain subordinate to trustworthy dictation behaviour:

- The voice box only reflects real states such as starting, listening,
  transcribing, copied, or an explicit error.
- It must not become a permanent chat bubble or fake waveform.
- Error, success, and privacy states need text/icon meaning as well as colour.
- Text previews remain optional for screen-sharing privacy.
- Do not reuse external product names, marks, copy, illustrations, screenshots,
  or exact layouts. The kit takes general cues—warm space, bounded actions, and
  calm progression—and gives them Vaani-specific colours, mark, and component
  rules.
