# User flows — Phase 2

## First run (current IME-first V1)

```mermaid
flowchart TD
  A[Open Vaani] --> B[Welcome]
  B --> C{On-device speech available?}
  C -- No --> C1[Explain device limitation]
  C -- Yes --> D[Explain microphone use]
  D --> E{Permission granted?}
  E -- No --> E1[Real Android permission sheet]
  E1 --> E2{Granted?}
  E2 -- No --> E3[Not now + repair later]
  E2 -- Yes --> F[Enable Vaani keyboard]
  E -- Yes --> F
  F --> G{IME enabled?}
  G -- No --> G1[Android IME settings]
  G1 --> G2[Re-check on return]
  G2 --> G
  G -- Yes --> H[Test field + choose Vaani]
  H --> I[Hold Send → speak → release]
  I --> J{Insert succeeds?}
  J -- Yes --> K[Mark setup complete → Home]
  J -- No --> L[Preserve transcript → Copy or retry]
```

## Returning user

```mermaid
flowchart LR
  A[Focus text field in another app] --> B[Select Vaani keyboard]
  B --> C[Hold Send]
  C --> D[Immediate Starting/Listening state]
  D --> E[Speak; real level only]
  E --> F[Release]
  F --> G[Finishing]
  G --> H[Insert text]
  H --> I[Small acknowledgement → disappear]
```

## Failure recovery

```mermaid
flowchart TD
  A[Recognized text] --> B{InputConnection accepts?}
  B -- Yes --> C[Success]
  B -- No --> D[Recovery surface]
  D --> E[Copy]
  D --> F[Try again]
  D --> G[Dismiss]
  E --> H[Text remains user-controlled]
  F --> B
  G --> I[No insertion]
```

## Future coexisting invocation

The future overlay must consume the same `DictationState`, STT boundary, cleanup boundary, and insertion/recovery contract. It must not require a second formatter or a second transcript lifecycle. Its implementation is intentionally not started in this phase.

