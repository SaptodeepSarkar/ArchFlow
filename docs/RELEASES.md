# Delivery surfaces

Vaani has two independently buildable products.

## Android APK

Build the debug APK with `make android-debug`. Its output is
`android/app/build/outputs/apk/debug/app-debug.apk`. Build the unsigned release
APK with `make android-release`; sign it with the project release key before
publishing it to a GitHub Release. Do not commit APKs or keystores.

Users should download only a signed release APK with a published SHA-256 digest.
The APK obtains model packages through the app's verified model-release flow;
model weights are not bundled in Git or the repository release artifact.
Firebase account/sync is optional: a local-only build does not require a
`google-services.json`; release maintainers add that private file before
building an account-enabled APK.

## Linux / QML desktop

For a source install on Arch + Hyprland:

```sh
make install-desktop
./tools/setup-stt.sh
systemctl --user enable --now vaanid.service
```

The installer places the app-owned Hyprland include at
`~/.config/hypr/vaani.conf`. Add this single line to the user's Hyprland config:

```ini
source = ~/.config/hypr/vaani.conf
```

For a distributable Arch package, run `./tools/package-local.sh`. It packages
the QML files, service, desktop entry, and app-owned Hyprland configuration;
it never edits a user's dotfiles or bundles model weights.
