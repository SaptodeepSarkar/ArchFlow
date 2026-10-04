# Prompt to give the testing agent

Test the current ArchFlow/Vaani Android and native Linux apps as an actual user.
Read `AGENTS.md`, `docs/NATIVE_APP.md` and `docs/qa/phase1/README.md` first.
Do not train models, redesign Windows, add internet relays or claim universal
Wayland insertion. Preserve the user's config, vocabulary, keys and model packs;
use disposable profiles and synthetic dictation. Never collect private field text,
recordings, pairing tokens or key material in the report. Do not push changes.

1. Record commit, build commands/results, APK hash/signature, runtime/model hashes,
   OS, hardware, RAM, Android API/ABI, compositor, audio path and permissions.
   Build with Rust/Cargo, GTK4/libadwaita/gtk4-layer-shell and Android JDK17/SDK35.
   Run `cargo test --workspace`, native GUI smoke and Android unit/instrumented
   tests. An emulator is acceptable for interaction; mark energy results as
   unmeasured until a physical phone/laptop is profiled.
2. Install the native desktop from source and a verified bundle, online and
   offline. Reinstall with an existing config/model/personalization profile.
   Check corrupted archive/hash, wrong architecture, missing runtime libraries,
   interrupted download and rollback: no working build or user data lost.
3. Use all five pages on each platform. Check small windows/screens, scrolling,
   keyboard/navigation, permissions, launcher/logo and white/sky/apricot colors.
   Save valid/invalid settings; externally change/malformed TOML; confirm unknown
   fields/comments survive and conflicts fail clearly. Install/select speech and
   formatter models; verify checksum, cancellation, old-model preservation and
   clear fallback for absent/corrupt/incompatible packs.
4. Dictate synthetic English/Hindi/Bengali and source-grounded formatting cases:
   negation, uncertainty, intentional repetition, quoted commands, corrections,
   spoken lists and links. Compare recognizer text, formatter backend and final
   output; unsupported meaning changes are critical failures. Exercise overlay
   and optional Android IME independently and concurrently. Cancel at recording,
   loading, inference and formatting. Switch A→B→A, change selection, close/hide
   IME, lock/background and retry rapidly. No stale insertion, unsafe full-field
   rewrite or simultaneous microphone ownership is allowed. Unsupported desktop
   targets must offer safe copy/review.
5. Measure baseline versus candidate on the same physical devices/models:
   30–60 minute idle, accessibility-enabled idle, ten identical dictations,
   cancellation and retention expiry. Use `tools/profile-android-phase1.sh` plus
   device-supported Perfetto/power tools and Linux process/energy sampling.
   Report repeated CPU including helpers, wakeups, network, mic lifetime,
   PSS/RSS/VRAM peaks, cold/warm load and result latency, battery/energy and
   thermal variance. Confirm no model load at launch, Economy unload after use,
   bounded retention and safe low-memory cleanup. Distinguish cached handles
   from OS file caches; JNI cancellation may wait for native inference to finish.
6. Migrate real-shaped disposable legacy personalization on both platforms.
   Check encrypted files, old-store retirement after verified persistence,
   tombstones/stable IDs and restart. Lock/remove keyring/Keystore, tamper or
   truncate ciphertext and interrupt migration: preserve files and fail closed.
   Do not downgrade an encrypted profile into a legacy build.
7. Test Android–Android, Linux–Linux and Android–Linux in both directions on
   reachable LANs. Android emulator addresses are usually NATed: configure
   legitimate host/bridge reachability or use physical devices; do not expose ADB
   or pairing ports publicly. Test QR scan and manual code, fingerprint mismatch,
   wrong token, two-minute expiry, single use, cancel, connection loss, malformed
   and oversized bundles. Receiver approval must precede merge. Transfer
   vocabulary, snippets/links, replacements and optional portable preferences.
   Repeat and reverse transfer, edit conflicts and deletions: no duplicates or
   resurrection. Confirm no listener after leaving Receive and no Firebase,
   account, push or periodic network activity. Preferences are approved snapshots,
   not independently clocked records; report partial preference/record failures.

Deliver `docs/qa/device-test-report.md`: a short user-experience summary, exact
passed/failed/skipped counts, environment and reproducible evidence, measurements
with units/trials, a prioritized bug table (severity, steps, expected/actual,
impact, evidence), and release recommendation. Separate cloud, emulator and
physical findings. Never convert an unrun scenario into a pass. If permitted,
fix confirmed defects in small local commits and rerun affected checks; retain
before/after evidence. State missing access or hardware plainly.
