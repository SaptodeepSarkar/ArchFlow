# Android UI screenshot sweep

Captured from the debug APK on `Pixel_16_Play(AVD) - API 35` using ADB on
2026-09-19. The sweep covers the four onboarding moments, permission recovery,
Android keyboard setup/picker screens, the real Vaani keyboard, and the three
main app surfaces at multiple scroll positions.

| File | State |
| --- | --- |
| `01`–`05` | Onboarding welcome, microphone-needed, permission dialog, microphone-ready, keyboard setup |
| `06`–`07` | Android input-method settings before and after enabling Vaani |
| `08`–`10` | Rehearsal field, keyboard picker, and selected Vaani field with the live keyboard |
| `11`–`12` | Home top and scrolled bottom |
| `13`–`15` | Personalize top, middle, and bottom |
| `16`–`19` | Settings top, middle, bottom, and top after returning |
| `20` | Onboarding welcome in landscape |

The screenshots are visual QA evidence, not product marketing assets. They are
kept alongside the code so future UI changes can be compared against a real
device layout.
