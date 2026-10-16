# UI

`pill.qml` is the Vaani pill (QtQuick, loaded by QuickShell). Preview it standalone:

```sh
qmlscene UI/pill.qml
```

## Contract with the key service

- Key service sets `state` (`listening` | `transcribing` | `writing` | `error`) and `words` (4-word trailing window).
- `cancelRequested()` aborts the run: no formatting pass, straight to offload.
- The pill hides before typing starts (Wayland focus rule); it never grabs keyboard focus itself.
