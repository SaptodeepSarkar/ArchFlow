import QtQuick
import Quickshell
import Quickshell.Io

QtObject {
    id: theme
    property var scheme: ({})
    readonly property bool dynamic: Object.keys(scheme).length > 0
    function pick(key, fallback) {
        var value = scheme[key];
        return typeof value === "string" && /^#?[0-9a-fA-F]{6}$/.test(value) ? "#" + value.replace(/^#/, "") : fallback;
    }
    readonly property color background: pick("background", "#101218")
    readonly property color surface: pick("surfaceContainer", "#1B1E27")
    readonly property color text: pick("onSurface", "#F0F0F7")
    readonly property color muted: pick("onSurfaceVariant", "#B7BAC9")
    readonly property color accent: pick("primary", "#C3B4FF")
    readonly property color outline: pick("outlineVariant", "#3D4050")
    readonly property color error: pick("error", "#FFB4AB")
    property FileView source: FileView {
        path: Quickshell.env("VAANI_THEME_FILE") || ((Quickshell.env("XDG_STATE_HOME") || (Quickshell.env("HOME") + "/.local/state")) + "/caelestia/scheme.json")
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try { theme.scheme = JSON.parse(text()).colours || {}; }
            catch (e) { theme.scheme = {}; }
        }
        onLoadFailed: theme.scheme = ({})
    }
}
