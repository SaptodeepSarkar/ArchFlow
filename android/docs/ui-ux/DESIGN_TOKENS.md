# Vaani Android design tokens

The palette is an original, restrained remix of the visual cues observed in Wispr Flow's public CSS (ink `#1A1A1A`, warm cream `#FFFFEB`, lilac `#F0D7FF`, orange `#FFA946`, green `#034F46`). It is not a copy of its identity, assets, layouts, or typography. Vaani shifts the neutral warmer and makes forest ink/amber the semantic pair.

## Color roles

| Token | Light | Dark | Use |
|---|---|---|---|
| `canvas` | `#FFF9E8` | `#111816` | app background |
| `surface` | `#FFFDF7` | `#1B2522` | cards and fields |
| `surfaceRaised` | `#F2EEE2` | `#26312E` | secondary controls / keyboard controls |
| `ink` | `#18352F` | `#F5F1E5` | primary text |
| `muted` | `#63736E` | `#B7C1BB` | supporting text |
| `outline` | `#D9DDD3` | `#3A4743` | dividers and borders |
| `accent` | `#E7A43B` | `#F0B85F` | primary action / dictation action |
| `accentOn` | `#2A2114` | `#1B241F` | text/icon on accent |
| `ready` | `#397254` | `#9BC6A8` | actual ready state only |
| `warning` | `#8A5A13` | `#F0B85F` | degraded action required |
| `error` | `#A64032` | `#FFB4A5` | actual failures only |

## Geometry and type

```text
spacing: 4, 8, 12, 16, 20, 24, 32 dp
small shape: 12 dp
medium shape: 16 dp
large shape: 20 dp
pill: 99 dp
compact screen padding: 20 dp
primary/action minimum height: 52 dp
keyboard key minimum height: 48 dp
```

Typography uses Android system sans: bold title, medium section/action labels, regular body, muted metadata. No serif display font, decorative font, or all-caps section wall.

## Motion

```text
acknowledgement: 150–250 ms
surface transition: 220–300 ms
overlay collapse: 200–350 ms
continuous audio level: real callback only; no fake idle movement
```

All decorative motion stops when animators are disabled. Stop/cancel never waits for an animation.

