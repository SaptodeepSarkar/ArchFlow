# Vaani Android Onboarding: Lead Product Design Proposal & Design System Specification

**Theme:** *"Your thumbs are getting a break."*
**Platform:** Android Native (Material 3 + Editorial Tactile + Deadpan Wit)
**Core Interaction:** Custom Keyboard / IME with Hold-to-Talk (`Hold` ~220ms → `Talk` → `Release` → Text Inserted without auto-send).

---

## 1. Visual Foundation & Design Tokens

### Color Palette (Warm Editorial / Golden Hour Tactile)
*No neon blues, no glowing AI orbs, no purple gradients. Grounded, human, organic warmth.*

| Token Name | Light Mode | Dark Mode | Semantic Role |
|---|---|---|---|
| `surface-bg` | `#FBF9F5` (Warm Alabaster / Cream) | `#141613` (Deep Olive Charcoal) | Window background & canvas |
| `surface-card` | `#F2EEE7` (Soft Linen Cream) | `#1E201C` (Muted Warm Carbon) | Cards, paperwork sheets, keyboards |
| `surface-card-subtle` | `#E8E2D8` (Warm Bisque) | `#272A24` (Subtle Olive Slate) | Inset fields, inactive keycaps |
| `text-primary` | `#1A1D1A` (Deep Forest Charcoal) | `#F6F4EE` (Warm Off-White) | Display titles, prominent copy |
| `text-secondary` | `#5C6159` (Muted Olive Khaki) | `#A2A79E` (Warm Mineral Grey) | Instructions, factual captions |
| `accent-gold` | `#D97706` / `#C26700` (Warm Amber Sand) | `#EAA33A` (Warm Sunlit Gold) | Focus states, cursor, listening pulse |
| `accent-green` | `#2D5A3D` (Subtle Pine Green) | `#5D8D6E` (Muted Sage Green) | Verified checkmarks, stamped approval |
| `accent-error` | `#B33927` (Brick Terracotta) | `#E06A55` (Muted Terracotta) | Genuine error states, recovery prompts |
| `cursor-color` | `#D97706` (Amber Accent) | `#EAA33A` (Golden Accent) | The recurring blinking character `|` |

### Typography Scale (Editorial Sans-Serif / Clean Android System)
- **Display 1 (Cold Open):** 40sp / line-height 46sp, Weight 700 (Letter-spacing -0.02em)
- **Headline 1 (Moment Titles):** 28sp / line-height 34sp, Weight 650 (Letter-spacing -0.015em)
- **Subheadline / Gestures:** 20sp / line-height 26sp, Weight 600
- **Body Large (Copywriting):** 16sp / line-height 23sp, Weight 400
- **Body Small / Captions:** 13sp / line-height 18sp, Weight 400 (Letter-spacing +0.01em)
- **Interactive Button:** 15sp, Weight 600 (Letter-spacing +0.02em, Centered)

---

## 2. The Recurring Visual Motif: The Cursor `|`
The blinking cursor is not an illustrated mascot with eyes; it is a live typographic character that bridges each phase:
- **Moment 1:** `Typing?|\nIn this economy?`
- **Moment 2 (Check):** `Checking your phone's ears...|` → changes to steady pulse
- **Moment 3 (Mic):** `Microphone access|`
- **Moment 4 (IME):** Transforms into the baseline indicator on the active paperwork card
- **Moment 6 (Tutorial):** Morphs into a dynamic audio level line between `HOLD → TALK → RELEASE`
- **Moment 7 (First Dictation):** Blinks in the live editable test box
- **Moment 8 (Success):** `My thumbs are officially on vacation.|` (Quiet final blink).

---

## 3. Complete Storyboard & Flow Architecture

```
[M1: Cold Open]
   │  "Typing? In this economy?|"
   │  CTA: [ Give my thumbs a break ]
   ▼
[M2: Device Speech Check]
   ├── Checking... (Local Android SpeechRecognizer check)
   ├── SUCCESS: "✓ Your phone has ears." ──> Auto-advances
   └── FAILURE: "Your phone isn't ready for local dictation." (Technical fallback/explanation)
   ▼
[M3: Microphone Permission]
   ├── "I need the microphone. Shocking, I know."
   ├── CTA: [ Allow microphone ] ──> Android OS Permission Dialog
   ├── GRANTED: "Nice. You do, in fact, have a voice."
   └── DENIED: "Microphone is off. Vaani can't listen without it." [ Try again ] / [ Open Settings ]
   ▼
[M4: Android Paperwork - IME Enable]
   ├── Stack of geometric "paperwork" cards slides up
   ├── "Now for the fun part. Android paperwork."
   ├── Step 1: "Enable Vaani" -> [ Open keyboard settings ]
   ├── Return Check:
   │    ├── Not enabled: "Not quite. Vaani is still disabled." [ Open settings again ]
   │    └── Enabled: "✓ Paperwork approved. Somehow." (STAMP: DONE)
   ▼
[M5: Choose Vaani IME]
   ├── Step 2: "Choose Vaani as your keyboard." -> [ Choose keyboard ] (OS IME Picker)
   └── Clarification: "You can switch keyboards anytime using Android's keyboard picker."
   ▼
[M6: Teach The Gesture - Interactive Sandbox]
   ├── "Here's the entire instruction manual."
   │    HOLD (220ms) ──> TALK ──> RELEASE
   │    "That's it."
   ├── Micro-Interactive Mini Keyboard: Send key hold training
   ├── Real audio level animation (RMS) -> Release triggers "Finishing…"
   └── DOES NOT send message. Accessible Cancel touch target.
   ▼
[M7: First Real Dictation (The Punchline)]
   ├── "Your turn. Say: 'My thumbs are officially on vacation.'"
   ├── User holds Send key on Vaani IME, speaks the exact sentence, releases
   ├── SpeechRecognizer processes locally
   ├── SUCCESS: "My thumbs are officially on vacation.|" inserted!
   └── FALLBACKS:
        ├── Silence: "I heard the silence perfectly. Try saying something."
        ├── Unrecognized: "Didn't catch that." [ Try again ]
        └── Insertion drop: "Your dictation is safe: [text]" [ Copy ]
   ▼
[M8: Quiet Understated Success]
   ├── Headline: "That's Vaani."
   ├── "Hold. Talk. Release."
   ├── Deadpan: "Your thumbs are now on reduced duty."
   ├── Visual: The Spacebar / Send key visually reclines/clocks out
   └── CTA: [ Start dictating ]
```

---

## 4. Hardware, Motion & Haptic Specs
- **Button Press:** Light tactile tick (`HapticFeedbackType.KEYBOARD_TAP`).
- **Hold Threshold (220ms):** Medium tactile confirmation (`HapticFeedbackType.CONFIRM`). Send button morphs with subtle amber highlight.
- **Audio Capture:** Compact 4-bar reactive RMS level line (no fake looping audio waves).
- **Key Release:** Light confirmation, waveform stops instantly, state displays `Finishing…`.
- **Cancel Gesture:** Distinct warning click (`HapticFeedbackType.REJECT`), clearing audio buffer without insertion.
- **Paperwork Stamp:** Crisp double-click haptic on IME enablement verification.
