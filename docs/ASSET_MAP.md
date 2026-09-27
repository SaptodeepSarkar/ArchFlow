# Asset and screenshot map

Assets are grouped by consumer. Do not move a runtime asset merely to remove a
duplicate: Android resources and QML resources are packaged by different build
systems and must remain at their platform-local paths.

| Location | Consumer | Status |
| --- | --- | --- |
| `brand/` | source brand rules and mark assets | canonical brand source |
| `assets/branding/` | reusable project-brand exports | shared source assets |
| `assets/generated/onboarding/` | reviewed editorial source/export archive | provenance; not loaded at runtime |
| `ui/assets/` | Quickshell/QML overlay and onboarding | Linux runtime asset copies |
| `android/app/src/main/res/drawable-nodpi/` | Android Compose onboarding | Android runtime asset copies |
| `website/assets/` | marketing site | website-only assets |
| `docs/qa/android-screenshots/` | dated verification evidence | retain only named QA milestones |
| `docs/references/` | research/reference material | never runtime assets |

New screenshots go under `docs/qa/<platform>-screenshots/YYYY-MM-DD/` only
when they support a test result, bug report, or release review. Temporary
captures belong outside the repository and remain ignored by `docs/screenshots/`.
