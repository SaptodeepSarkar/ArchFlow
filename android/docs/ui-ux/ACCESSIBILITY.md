# Accessibility implementation notes

## Current increment

- System status/navigation bars are visible and handled through insets.
- Primary app actions are 52 dp high; keyboard and recovery actions are 48 dp high.
- Icon-only Send and Shift controls have content descriptions.
- The listening level has a semantic description and is not announced frame-by-frame.
- Dictation state is represented by text (`Starting`, `Listening`, `Finishing`, recovery), not color alone.
- Reduced animator settings skip the onboarding flow animation.
- Large text is allowed to wrap in the scrolling control plane; fixed-height decorative surfaces remain a follow-up QA item.

## Required device QA

- TalkBack: announce only meaningful state transitions, never every ASR hypothesis.
- Font scale: 1.3× and 2.0× on onboarding, Home, Settings, and recovery.
- Landscape: keep the compact keyboard dictation state usable and preserve stop/cancel.
- Contrast: check both themes over the IME surface and over arbitrary target apps.
- Switch access/keyboard navigation: ensure focus order follows content → primary action → secondary action.
- Touch exploration: no icon-only action without a label and no target below 48 dp.

## Known lint debt

The Views touch-listener API still emits `ClickableViewAccessibility` warnings even where `performClick()` is called from the gesture path. A follow-up should introduce a small custom touch button class that overrides `performClick()` and owns hold/release semantics, removing the warning without weakening gesture behavior.

