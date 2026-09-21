# Vaani art direction

Vaani is an Android dictation tool that turns speech into clean writing. Its
visual character is quiet editorial utility: confident, spacious, tactile, and
specific to an action the user can complete now.

## Original design rules

1. Lead each screen with one reading path: title, one explanation, one action.
2. Use `brand/ink` or `neutral/100` as the canvas. Reserve cobalt for the
   action/active-voice moment, and coral for small live or destructive signals.
3. Work on a 4 dp grid with generous 24–72 dp intervals. One full-width bottom
   CTA is at least 52 dp tall; secondary choices are text or thin outline.
4. Use one bundled variable sans family (Manrope preferred) across React Native
   and Kotlin. Onboarding titles are 40–48 sp semibold/bold; body is 17–19 sp;
   labels are 13–14 sp.
5. Make controls native, direct, and legible. Use simple vectors with one
   stroke weight; show real keyboard, microphone, overlay, and permission state.
6. Onboarding imagery is a text-free editorial background behind a dependable
   dark scrim. Top text and bottom action remain readable without the image.
7. Motion explains state only: 160–240 ms for navigation/press feedback; a
   listening treatment is driven by real audio and has a reduced-motion state.
8. Utility screens—settings, vocabulary, replacements, snippets, and keyboard—
   are intentionally undecorated and fast.

## Do not imitate

- Wispr Flow’s name, mark, copy, purple/lavender brand treatment, progress rail,
  looping decorative line art, bubble trigger, icon orbit, illustrations, app
  captures, or distinctive onboarding layouts.
- Generic AI gradients, fake waveforms, glowing blobs, robots, brains, card
  dashboards, and generated UI/keyboards/icons.
- Green as a primary Vaani colour, or multiple accent colours competing on one screen.
