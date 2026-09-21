# Vaani visual direction and image-generation directive

## Mission

Build Vaani as a focused Android dictation tool: speech becomes clean writing wherever the user can type. Its UI should feel calm, editorial, precise, and genuinely useful—not like a generic AI assistant, a chat app, or a Material-card dashboard.

The visual reference is the product feel shown in `docs/screenshots/good-screens/`: generous empty space, confident typography, restrained outlines, tactile controls, and a single dominant action. Do **not** copy Wispr Flow's logo, wordmark, screens, text, illustrations, or distinctive layouts. Take only the abstract visual grammar and create a recognisably original Vaani product.

The onboarding alone may use AI-generated editorial artwork. Product UI, icons, controls, diagrams, and keyboard keys must be built natively; do not generate them as images.

## Non-negotiable execution order

Do not start coding or generating imagery immediately.

1. Inspect **every** image in `docs/screenshots/good-screens/`, including its dimensions and file name.
2. Create `docs/references/good-screens-audit.md`. For each reference, record:
   - screen purpose and interaction state;
   - visual hierarchy (what the eye sees first, second, third);
   - spacing rhythm and alignment;
   - type scale and weight;
   - surface, border, shadow, colour, and contrast treatment;
   - motion implied by the composition;
   - elements that are specific to Wispr Flow and must **not** be copied.
3. Create a contact sheet at `docs/references/good-screens-contact-sheet.png` with file names beneath every thumbnail.
4. Write `docs/references/vaani-art-direction.md`, distilling the audit into original Vaani rules. It must include a short "do not imitate" list.
5. Write the generation plan below to `docs/image-generation-plan.md`. Only then generate the approved image set.
6. Put generated source PNGs in `assets/generated/onboarding/source/`; export the reviewed, resized WebP versions to `assets/generated/onboarding/`.
7. Build the onboarding with real text and controls over the assets. Never bake words, logos, UI buttons, status bars, or fake app screens into generated artwork.
8. Capture emulator screenshots and compare them side-by-side with the design rules. Fix the composition before proceeding to the next screen.

If `docs/screenshots/good-screens/` is missing or empty, stop and report the exact missing path. Do not invent references.

## Original Vaani rebrand

The old dark-green/lime logo palette is retired. Green must not remain as a primary brand or UI colour.

### Brand colours

| Token | Value | Use |
|---|---:|---|
| `brand/ink` | `#0C1020` | Primary canvas and dark logo background |
| `brand/cobalt` | `#526BFF` | Vaani primary, active voice state, key action |
| `brand/coral` | `#FF6B4A` | Small signal, recording/live emphasis, destructive state |
| `brand/cloud` | `#FFF7F1` | Primary button fill on dark artwork; light text surface |
| `brand/sky` | `#78C7FF` | Supporting highlight only, never a second primary action |
| `neutral/100` | `#F7F8FC` | Light canvas |
| `neutral/900` | `#171A26` | Dark text on light canvas |
| `neutral/600` | `#72788B` | Supporting text |
| `neutral/300` | `#D9DDE8` | Thin outline |

### Logo specification

- Keep the Vaani "V" concept, but redraw it as an original geometric mark.
- App icon: rounded-square `brand/cobalt` background, `brand/cloud` V glyph, and at most one small `brand/coral` signal detail.
- Wordmark: `brand/cloud` on dark screens and `brand/ink` on light screens. Do not use a green fill, a neon gradient, an audio-wave clone, or the Wispr Flow mark.
- The logo must remain legible at 24 dp. Test it at 24, 48, and 96 dp before approving it.

### Colour discipline

- Cobalt communicates action and active voice. Coral communicates live/urgent feedback. Sky is decorative support only.
- One screen gets one dominant accent. Do not put cobalt, coral, and sky on every component.
- Never use a multi-colour gradient as a shortcut for perceived polish.
- Keep normal app surfaces neutral. The colour energy belongs in moments of action, not every background.

## UI system to preserve

### Layout and type

- Use a 4 dp spacing base. Prefer 24, 32, 40, 56, and 72 dp gaps over dense 8–16 dp spacing everywhere.
- Keep an obvious reading path: title → explanation → action. Avoid competing cards.
- Use one clean variable sans family across React Native and Kotlin. Prefer Manrope or another single bundled variable sans; do not mix a decorative display font into settings screens.
- Onboarding display titles: 40–48 sp, bold/semibold. Body: 17–19 sp. Labels: 13–14 sp.
- Use a maximum of two text weights per content group.

### Components

- Primary action: one full-width bottom button, at least 52 dp tall, clear text label, strong contrast.
- Secondary action: text or a thin outlined control; never styled like a second primary CTA.
- Fields: thin outline, deliberate corner radius, label above or inside only when its state stays unambiguous.
- Icons: simple native vector icons with consistent stroke weight. Do not use generated icons.
- Use cards only to group a real setting or data item. A card must never exist merely to make an empty page look busy.

### Motion

- Motion has to explain a state transition: enter, press-and-hold, listening, processing, inserted, error.
- Use 160–240 ms for ordinary UI transitions. The listening visual may breathe slowly but must react to real RMS audio when audio is available.
- No looping blob, fake waveform, confetti, spinning neural network, or logo spectacle.
- Support reduced motion. Provide a static state for every animated asset/state.

## Image-generation rules

Use the available image-generation capability only for original editorial background art. Every generated asset must be:

- portrait, at least 1440 × 2560 px, with safe empty space for text at the top and CTA at the bottom;
- text-free, logo-free, watermark-free, and UI-free;
- recognisably aligned to the Vaani cobalt/coral/cloud palette, without green;
- atmospheric and tactile, using soft focus, real depth, diffuse light, and controlled grain;
- original: no references to Wispr Flow, no copied composition, no product logos, no exact recreation of any input screenshot;
- checked at 25% opacity behind actual UI so legibility is proven, not assumed.

Avoid prompts containing: "Wispr Flow", "copy", "clone", "app screenshot", "dashboard", "purple AI gradient", "robot", "brain", "neural network", "soundwave logo", "floating 3D blob", text, words, or a phone mockup.

### Required generation workflow

For each required asset:

1. Generate three clearly different composition candidates, not small random variations.
2. Put them in a numbered review sheet with the intended onboarding screen overlaid as a wireframe.
3. Evaluate: text-safe area, contrast, originalness, palette discipline, emotional tone, and visual weight.
4. Choose one candidate; make at most two targeted edits. Do not endlessly regenerate.
5. Export the approved final as lossless PNG and `webp` at the exact Android density sizes needed.
6. Record the final prompt, seed/variant information when available, source path, crop guidance, and approval reason in `docs/image-generation-log.md`.

## Required onboarding image set

These three images support onboarding only. Each screen has one image, one idea, and one action. The application must remain fully usable when an image is unavailable or reduced motion is enabled.

| ID and output name | Screen purpose | Composition and visual direction | Generation prompt |
|---|---|---|---|
| `01-arrival-voice-space.webp` | Welcome: introduce Vaani as calm, fast dictation. CTA: **Get started**. | A warm, intimate abstract workspace seen through a soft out-of-focus foreground; large dark/cobalt negative space in the upper third for the Vaani mark and title; a subtle coral reflection near the lower middle. It should suggest a thought becoming clear, without depicting an app or microphone. | `Original editorial still-life, portrait 9:16. An intimate abstract workspace at early evening, viewed through a gently blurred foreground. Deep ink navy and electric cobalt dominate, with one restrained coral reflection and soft cloud-white light. Premium editorial photography, shallow depth of field, tactile realistic grain, quiet and human, large calm negative space in upper third and lower fifth, no people in focus, no devices, no logos, no text, no UI, no green.` |
| `02-keyboard-handoff.webp` | Keyboard setup: explain that Vaani works where the user types. CTA: **Enable Vaani Keyboard**. | An abstract arrangement of translucent, rounded rectangular forms implying rhythm and typing—not literal keys. The central area stays calm for instructional copy; cobalt illumination comes from one side, with a small coral edge-light. | `Original abstract editorial image, portrait 9:16. Tactile translucent rounded rectangular forms arranged like a quiet rhythm, inspired by the physical feeling of typing but not showing a keyboard. Deep ink navy background, directional electric cobalt light from the left, a fine coral edge light, soft cloud-white highlights, sophisticated product-photography depth, generous clean central and bottom negative space, no phone, no app screen, no letters, no icons, no logos, no green.` |
| `03-ready-to-speak.webp` | Microphone permission and first-use readiness. CTA: **Allow microphone** or **Try a sentence**. | A luminous but restrained focal core low on the screen, with a clear dark top for text. It should convey breath, attention, and readiness through light and depth—not a literal microphone, waveform, or AI orb. | `Original atmospheric editorial image, portrait 9:16. A restrained luminous focal core made of soft layered light and translucent material low in the frame, suggesting breath and attention without looking like a microphone, soundwave, robot, brain, or glowing AI orb. Dark ink navy field, electric cobalt as the main light, a tiny coral live accent, cloud-white diffuse reflections, premium calm realism, soft grain, spacious dark top third and clear bottom CTA zone, no text, no logo, no UI, no green.` |

### Optional imagery—only after the required set passes review

Do not generate these during the first build. Generate only if a specific screen needs atmosphere and its use does not reduce clarity.

| Output name | Allowed use | Constraint |
|---|---|---|
| `voice-core-idle.webp` | Home empty state | Must be subtle and still; never become a mascot or fake live waveform. |
| `voice-core-listening.webp` | Real active listening state | Must be driven or visibly gated by real audio state; no animation when the microphone is off. |
| `permission-recovery.webp` | Permission recovery screen | Use abstract ambient art only; system permission instructions remain native text and controls. |

No generated art belongs in Vocabulary, Replacements, Snippets, Settings, or the native keyboard. Those surfaces need speed, clarity, and native controls—not decoration.

## Screen-specific UX requirements

### Onboarding (maximum four screens)

1. Welcome with `01-arrival-voice-space.webp`; only product promise and **Get started**.
2. Keyboard enable with `02-keyboard-handoff.webp`; launch the real Android keyboard settings intent and verify its result when the user returns.
3. Microphone readiness with `03-ready-to-speak.webp`; request permission only at the point it is needed, explain denial recovery plainly.
4. First successful dictation; show the real hold-to-speak interaction and success only after insertion completes.

Do not put vocabulary, snippets, replacement management, model settings, or a multi-option preference form in onboarding.

### App surfaces

- **Home:** quiet status and one useful next action. No fake live transcript or chat history.
- **Personalize:** separate Vocabulary, Replacements, and Snippets. These are utility surfaces, not onboarding pages.
- **Settings:** compact and utilitarian; no hero artwork.
- **Native keyboard:** dense, tactile, thumb-first. Hold for roughly 220 ms to begin speaking; release inserts the result. Its listening visual must follow real audio/session state.
- **Optional overlay:** Kotlin-native and opt-in. Explain the special Android permission truthfully. It must not be required for Vaani to work.

## Technical implementation boundaries

- Main app screens: React Native TypeScript.
- Native keyboard, overlay, Android settings intents, microphone/session lifecycle: Kotlin.
- Native overlay and `InputMethodService` UI: Kotlin/Compose. Do not try to put a React Native view into a system overlay or IME.
- Keep all shared colours, spacing, radii, and type values in `docs/design-tokens.json`; export matching TypeScript and Kotlin tokens.
- Use generated artwork only as a background layer with an adjustable native scrim. Copy must meet contrast requirements without relying on the image.
- Asset loading must not block first render. Include a plain-colour fallback for every image.

## Acceptance checklist

The task is complete only when all points are true:

- [ ] Every `good-screens` reference has an audit entry and appears in the contact sheet.
- [ ] The new Vaani mark has no green as a primary colour and is legible at 24 dp.
- [ ] Three approved onboarding images exist, are original, contain no text/UI/logos, and use the new palette.
- [ ] Every onboarding image has verified top text and bottom CTA safe areas.
- [ ] Onboarding has no more than four screens and validates keyboard/microphone setup rather than merely displaying instructions.
- [ ] No generic AI gradients, glowing blobs, card-grid dashboard, robot art, copied Wispr branding, or fake capabilities appear in screenshots.
- [ ] Screenshots exist for onboarding, permission denial/recovery, Home, Personalize, Settings, keyboard idle/listening/inserted, overlay off/on, small phone, large phone, and landscape.
- [ ] Screenshot review names concrete deviations and concrete fixes; it does not use empty labels such as “premium,” “clean,” or “polished.”
- [ ] The app works with generated imagery disabled.

## Final delivery report

At the end, provide:

1. the reference audit and the original Vaani design principles;
2. the logo rebrand summary and token table;
3. a table of every generated image, its purpose, prompt, path, and crop-safe zones;
4. before/after screenshots for every approved screen;
5. unresolved Android constraints, especially overlay permission and device-specific behaviour;
6. the next smallest implementation milestone.
