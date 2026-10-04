# Brand and website refresh — 4 October 2026

The prior site, brand kit, legacy SVG and pre-adaptive Android icon still used
inconsistent identities. The old site's demo also referenced a missing element.
The refresh unifies the canonical SVG, legacy SVG copy, site favicon, Android
vectors/header, GTK palette, tokens and brand reference.

The Speakmark uses two shapes: a rounded V and a detached speech dot. The site
uses original paper-note illustrations, explicit demo labels and accurate Linux
and Android build links. It avoids remote fonts and unsupported claims about
meaning-changing edits, inference speed or battery savings.

Verified in local Chromium:

- 1440, 1024, 768, 390 and 320 px viewports: no horizontal overflow, missing
  images or page JavaScript errors; all three example buttons work and exactly
  one stays selected.
- Keyboard skip link reaches main content; visible focus and reduced-motion
  styles are present.
- Axe WCAG 2 A/AA and 2.1 AA audit: zero automated violations at 1440 and 390 px,
  22 passing checks at each width. This does not replace a screen-reader audit.
- Desktop and mobile full-page screenshots inspected: `desktop.png`, `mobile.png`.
- Android debug APK assembled successfully; updated launcher resources and
  Compose header compile. Physical launcher-mask/device interaction unrun.
- Native GTK release build and Xvfb five-page smoke passed. Actual compositor
  launcher appearance remains a device check.

Graphify is not installed, so its graph was not refreshed. Production hosting
was not deployed or verified; changes are source assets on the `work` branch.
