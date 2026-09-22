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
    // Vaani brand-kit defaults. A Caelestia scheme may still override these
    // when explicitly supplied, but the app remains warm-paper by default.
    readonly property color background: pick("background", "#FDFBF8")
    readonly property color surface: pick("surfaceContainer", "#FFFDFB")
    readonly property color text: pick("onSurface", "#19161C")
    readonly property color muted: pick("onSurfaceVariant", "#827B87")
    readonly property color accent: pick("primary", "#6B3A85")
    readonly property color outline: pick("outlineVariant", "#E8E2E7")
    readonly property color error: pick("error", "#B34E4E")
    readonly property color lilac: "#E8DCFF"
    readonly property color apricot: "#FFD4A3"
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
