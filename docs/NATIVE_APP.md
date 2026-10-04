# Native Vaani: build, install and resource ownership

This implementation keeps the Rust dictation engine and Kotlin/Compose Android
app. Linux now launches `vaani-linux`, a Rust GTK4/libadwaita app; Quickshell is
not installed or invoked. Historical QML/assets remain in source for reference.
The Speakmark—a rounded V with a detached speech dot—is `brand/vaani-mark.svg`.
The shared identity and palette are documented in `brand/README.md`.

## Build and install

Linux build dependencies: Rust/Cargo, C/C++ toolchain, pkg-config, GTK4 >=4.8,
libadwaita >=1.2, gtk4-layer-shell, OpenSSL development libraries. Runtime:
those libraries, a working Secret Service keyring, PipeWire and the existing
clipboard/insertion tools. Hyprland integration remains compositor-specific;
unsupported targets use copy/review. GTK overlay requires layer-shell and does
not fall back to a focus-stealing normal window.

```sh
make desktop-release
./install.sh
./tools/build-native-runtimes.sh
install -m755 .vaani/native-runtimes/bin/* ~/.local/bin/
```

Add `~/.local/bin` to PATH. Open **Vaani Desktop**, install speech/optional
formatter models on Models, then select them in Settings. Start/stop the service
from Home; explicitly enable on login with `systemctl --user enable vaanid`.
For existing CT2/Python model installations keep the corresponding Python
runtime/venv. Their compatibility is preserved, not replaced with new weights.

To prepare a portable CPU build and optional offline models:

```sh
./tools/build-native-runtimes.sh
python3 tools/native-bundle.py build --runtime .vaani/native-runtimes/bin \
  --output /tmp/vaani-linux.tar.gz
# Optional: --models PATH with stt/base.bin, formatter/model.gguf,
# formatter_v6/model.v6tg laid out relative to PATH.
python3 tools/native-bundle.py install /tmp/vaani-linux.tar.gz \
  --sha256 TRUSTED_SHA256 --verify-only
python3 tools/native-bundle.py install /tmp/vaani-linux.tar.gz \
  --sha256 TRUSTED_SHA256
# Online uses the identical verified payload/install path:
python3 tools/native-bundle.py install https://YOUR_RELEASE/vaani-linux.tar.gz \
  --sha256 TRUSTED_SHA256
```

Obtain the archive digest from the trusted publisher independently; a checksum
inside an untrusted archive is not authenticity. Bundles are architecture and
runtime-library specific, not universally static Linux executables. Preflight
checks archive/hash/size, every payload digest, safe paths, architecture and
missing dynamic dependencies before installing. Existing personal config/data
and models are preserved; changed app-owned files are rolled back on failure.
Installation does not silently start a service or edit the main compositor config.
`VAANI_BIN_ROOT`, `XDG_CONFIG_HOME` and `XDG_DATA_HOME` support isolated installs.
Uninstall preserves user data. The source checkout remains the build-code record;
release maintainers can distribute its revision alongside the verified bundle.

The bundled `models/linux-models.json` reuses the existing published Android
artifact hashes and licenses, with Linux-compatible GGML/GGUF/V6 filenames.
The GUI selects these entries directly or accepts a custom catalog and local
asset for offline installation. Model install validates declared size/SHA256 and
format, keeps the previous model and publishes only a complete verified file.
It does not load models. Android explicit online downloads use existing checked
release metadata; manual document imports validate format/size and should only
come from a trusted source (they do not authenticate a publisher).

## Ownership and behavior

- `vaani-core`: source-grounded rendering, config validation, stable record and
  deterministic tombstone merge contracts; authenticated encrypted storage.
- `vaanid`: recording/session/focus/delivery ownership. Its typed local socket
  exposes settings reload and personalization import/export. Audio and dictated
  text are not new settings/transfer payloads.
- `vaani-local`: `settings` preserves comments/unknown TOML and checks external
  changes; `models` verifies install; `pairing` owns one temporary TLS receiver;
  `ipc` owns socket requests/subscription. GTK Settings, Personalization, Models
  and overlay are separate modules. The shell owns navigation and UI events.
- Android `features`: Home, Models, Personalization, Settings and Devices.
  `DictationSessionGate`/ownership invalidate stale callbacks and old editors;
  `ModelLifecycle` serializes load/inference/unload. No eager launch load.
  Economy releases after each operation; Balanced retains at most 120 seconds.
  Low memory requests unload after active inference. JNI calls may finish before
  cancellation cleanup can release their handles safely.
- Linux models run in inference workers only after a nonempty dictation request.
  Economy releases model processes after each operation. Native Whisper/GGUF
  helpers use private inherited pipes and optional retention capped at 120 seconds,
  with an expiry timer and exclusive inference leases. Older CLI-only installations
  fall back to one-shot processes. CT2/Python backends retain their existing idle
  reaper; physical-device timing and memory measurements remain a release gate.

Linux data uses AES-256-GCM and a Secret Service key; Android uses AES-256-GCM
with a nonexportable Keystore key and AtomicFile. Legacy local personalization
and Linux outbox migrate only after validated encrypted persistence. Missing
keys, locked keyrings and corrupted ciphertext preserve files and fail closed.
Encrypted Linux operations acquire a private file lock to reject simultaneous
repositories; Android read/modify/write uses the shared repository lock.
Backup ciphertext together with its platform key recovery mechanism; ciphertext
alone cannot be restored if keys are lost. No plaintext/raw-key fallback exists.

## Local transfer

Receive binds a chosen local IPv4 address only while explicitly open. Its QR
contains protocol version, IP/port, exact certificate SHA256, random 256-bit
capability token and two-minute expiry. TLS 1.3 pins that certificate; no global
CA bypass applies to other connections. Frames are bounded to 900,000 bytes and
2,000 records. Identity/schema/size/deletion state and portable preference keys
are validated before staging. The receiver must approve before applying records.
Transfers include vocabulary, snippets/links and replacements with stable IDs,
Lamport clocks and retained tombstones. Repeated merges converge without duplicate
IDs or resurrecting older deleted values. Portable preferences are optional,
explicitly approved snapshots; preference and record changes are separate durable
operations, so errors between them can require retry. No background discovery,
account, Firebase, FCM, relay or periodic sync remains.

Cross-device interaction, real Android Keystore recovery, real Wayland focus/
insertion and physical energy/thermal measurements require the testing prompt.
Cloud tests and loopback TLS tests do not establish those completion gates.
