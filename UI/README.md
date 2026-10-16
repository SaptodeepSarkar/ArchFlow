# UI

`pill.qml` is the Vaani pill (QtQuick, loaded by QuickShell). Preview it standalone:

```sh
qmlscene UI/pill.qml
```

## Contract with the key service

- Key service sets `state` (`listening` | `transcribing` | `writing` | `error`) and `words` (full transcript so far).
- Pill displays `trail(words)`: the last `trailingWindow` words (`4` by default, overridable from `.conf`).
- `cancelRequested()` aborts the run: no formatting pass, straight to offload.
- The pill hides before typing starts (Wayland focus rule); it never grabs keyboard focus itself.
