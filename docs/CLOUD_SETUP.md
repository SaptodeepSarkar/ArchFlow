# Reusable cloud setup

This cloud workspace is a Linux container, distinct from the target laptop in
ADR-001. It has no connected Android device or target Wayland/PipeWire session.

Install Rust stable through rustup, JDK17, Android SDK35/build tools35, and Gradle
8.9. Verify downloaded toolchains against the publisher's checksums. Configure
Android SDK paths through ANDROID_HOME/local.properties, and keep Gradle/SDK
caches in writable directories. Use the network's trusted CA/proxy configuration;
do not disable TLS validation. Never commit local.properties or signing secrets.

Linux native build dependencies: C/C++, CMake, pkg-config, OpenSSL, libsecret,
GTK4 >=4.8, libadwaita >=1.2, gtk4-layer-shell and system development headers.
An unprivileged cloud worker can extract signed distribution packages into a
local prefix and configure PKG_CONFIG_PATH/LIBRARY_PATH/LD_LIBRARY_PATH; a
normal development machine should install its distribution's development packages.
Use Xvfb and a private D-Bus session for GUI construction smoke tests. A smoke
pass does not test the Wayland overlay, microphone or system keyring migration.

```sh
cargo test --workspace
make desktop-release
./tools/build-native-runtimes.sh
python3 tools/test-native-bundle.py
cd android
./gradlew testDebugUnitTest assembleDebug compileDebugAndroidTestKotlin
```

For actual device tests, follow TESTING_AGENT_PROMPT.md. Local model/toolchain
caches, APKs and built runtimes stay outside commits. Release build artifacts need
independent hashes, provenance and target-distribution validation.
