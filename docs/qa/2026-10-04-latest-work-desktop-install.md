# Latest work-branch desktop installed on target laptop

Fetched `origin/work` at `c2dd3f8b` and merged it with current main fixes
at `114c8881`. Installed release binaries `vaani-linux`, `vaani-desktop`,
`vaanid`, `vaani`, and `vaani-worker` user-locally, plus the refreshed icon.
The current formatter protocol sidecars were preserved. No model selection,
weights, training source, or personal configuration was changed.

Build used two Cargo jobs under a 4 GiB maximum/no-swap user scope, with
the existing user-local gtk4-layer-shell 1.3.0 library and explicit rpath.
GTK 4.22.5 and libadwaita 1.9.4 were present. Build completed successfully.
Nine local-app tests and nineteen daemon tests passed; three hardware/model
tests were ignored. Existing compiler warnings remain.

Installed GTK binary SHA-256:
`f44f128b67c521ea180dcde5576331b3cfac599e0d20a1e9ad392b781d80afef`.
Configuration hash before and after:
`201c1de456d23128c76415201fe603d5da29b0b6e24bea031b11426ca5ae30b7`.

Daemon was IDLE before restart and returned IDLE afterward. Launched Vaani
Desktop through its installed launcher. Hyprland confirmed a mapped
`org.vaani.Desktop` window titled `Vaani — Your voice, your device`, size
908×1038. App and daemon units were active; layer-shell resolved correctly.
No real microphone capture, insertion, or physical HUD interaction was
performed by this installation check. Those are not inferred from unit tests.
