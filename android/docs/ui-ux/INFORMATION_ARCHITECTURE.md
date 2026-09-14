# Information architecture — Phase 2

Vaani is a control plane for a system-wide capability. The keyboard is the daily surface; the app is where readiness, trust, and customization are managed.

## Navigation

```text
Home
  ├─ readiness / next blocker
  ├─ test dictation
  ├─ keyboard + speech status
  └─ privacy entry

Settings
  ├─ Dictation
  ├─ Appearance
  ├─ Keyboard integration
  ├─ Privacy & data (factual, current capabilities only)
  └─ About
```

Personalize and History are intentionally not exposed yet. Their underlying storage/matcher/retention contracts are absent. When Vocabulary, Snippets, and Replacements become real, add one `Personalize` destination. Add `History` only when retention is explicit and local persistence is shipped.

## Home hierarchy

1. `Vaani` app bar.
2. One readiness state: `Ready` or the single highest-priority blocker.
3. One primary action.
4. Compact quick status rows.
5. Privacy explanation and links to settings.

No KPI cards, productivity scores, model percentages, or marketing carousel.

## Adaptive behavior

- Compact phones: bottom navigation with Home and Settings.
- Widths above a future adaptive threshold: cap the content column; consider a rail only after a third real destination exists.
- Forms and future personalization lists should use a max readable width instead of stretching to the display edge.

