# Native GTK desktop installation on the target laptop

Installed source revision: `24fa56f8` (merges `origin/work` into the V6 main
line). The merged workspace Rust tests passed, with three opt-in hardware/model
tests ignored. Android was not built in this environment.

`install.sh` completed its locked release workspace build and GTK native-ui
build with two Cargo jobs, under a 4 GiB memory limit and no swap. Installed
`vaani-linux` SHA-256 matches the built artifact:
`ca03ad2f39053081b57d3c0b905fbe8180facacc01b8b7e450824655a4229b8d`.

GTK4 4.22.5 and libadwaita 1.9.4 were already installed. The missing
gtk4-layer-shell dependency was built from upstream v1.3.0, revision
`1c963c51514581c41b9bdae08cdf69171265cdda`, into the user-local
`~/.local/share/vaani/runtime/gtk4-layer-shell-1.3.0/` prefix. The binary embeds
that library directory as its runtime search path; `ldd` resolves the library.
No system package upgrade was performed.

The existing config SHA-256 is identical before and after installation:
`201c1de456d23128c76415201fe603d5da29b0b6e24bea031b11426ca5ae30b7`.
The launcher opened a mapped `org.vaani.Desktop` window titled
`Vaani — Your voice, your device` (908×1038). It exited successfully after
approximately 49 seconds. The installed daemon was started and responds to
doctor/status in IDLE; doctor finds `vaani-linux` and a valid V5 STT package.
No microphone recording or end-to-end dictation measurement was performed.

This verifies application installation and launch, not V6 model promotion.
Existing model selections are preserved. The separate formatter training scope
remained active during installation.
