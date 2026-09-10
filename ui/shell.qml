// Vaani overlay + settings shell (Quickshell config "vaani").
// Verified against Quickshell 0.3.1 (installed): PanelWindow via default
// Quickshell import, WlrLayershell attached props, Quickshell.Io Socket +
// SplitParser for event-driven IPC. No status polling loops anywhere.
//
// The daemon owns all state; this process exits when neither overlay nor
// settings is needed (see DaemonBridge.shouldStayAlive).
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Scope {
    id: root

    property string sockPath: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/vaani/control.sock"
    property string state: "IDLE"
    property string statusText: ""
    property real amplitude: 0
    property var ampHistory: []
    property int elapsedSecs: 0
    property bool showSettings: (Quickshell.env("VAANI_OPEN_SETTINGS") || "") === "1"
    property bool hidePreview: false
    property string pendingText: ""
    property var settingsApi: null
    property string provisional: ""
    property int committedWords: 0

    function send(obj) {
        obj.protocol_version = 1;
        obj.request_id = "qml-" + Math.floor(Math.random() * 1e9);
        sock.write(JSON.stringify(obj) + "\n");
        sock.flush();
    }

    function handleLine(line) {
        if (!line || !line.trim)
            return;
        var msg;
        try {
            msg = JSON.parse(line);
        } catch (e) {
            return;
        }
        // Snapshot (first line per connection) has state but no event/op.
        if (msg.event === "state" || (msg.state && !msg.event && !msg.ok && msg.event !== undefined)) {
            applyState(msg);
            return;
        }
        if (msg.event === "provisional") {
            var tail = (msg.data && msg.data.tail) || "";
            var hidden = msg.data && msg.data.hidden;
            root.provisional = hidden ? "" : String(tail).slice(-120);
            root.committedWords = (msg.data && msg.data.committed_words) || 0;
            if (hidden)
                root.statusText = "preview hidden";
            return;
        }
        if (msg.event === "amplitude") {
            root.amplitude = msg.amplitude || 0;
            var h = root.ampHistory.slice(-24);
            h.push(root.amplitude);
            root.ampHistory = h;
            return;
        }
        if (msg.event === "pending_expired") {
            root.pendingText = "";
            return;
        }
        // Responses carry ok/state/message/data.
        if (msg.ok !== undefined) {
            if (msg.state)
                root.state = msg.state;
            if (msg.message)
                root.statusText = msg.message;
            if (msg.data) {
                if (msg.data.text !== undefined)
                    root.pendingText = msg.data.text;
                else if (root.settingsApi)
                    root.settingsApi.routeData(msg.data);
            }
            return;
        }
        if (msg.state) {
            root.state = msg.state;
            if (msg.message)
                root.statusText = msg.message;
        }
    }

    function applyState(msg) {
        if (msg.state)
            root.state = msg.state;
        if (msg.message)
            root.statusText = msg.message;
        if (msg.data && msg.data.text !== undefined)
            root.pendingText = msg.data.text;
        if (root.state === "RECORDING") {
            elapsedTimer.restart();
            if (msg.event === "state" && msg.message === "Listening") {
                root.provisional = "";
                root.committedWords = 0;
            }
        } else {
            elapsedTimer.stop();
        }
        // On-demand UI residency: exit when nothing needs us.
        if ((root.state === "IDLE" || root.state === "CANCELLED") && !root.showSettings)
            Qt.quit();
    }

    Timer {
        id: elapsedTimer
        interval: 1000
        repeat: true
        onTriggered: root.elapsedSecs += 1
    }

    // Reconnect with bounded backoff; exit when daemon is gone and no
    // settings window is open (on-demand UI residency).
    Timer {
        id: reconnectTimer
        interval: 1500
        repeat: false
        onTriggered: {
            if (!sock.connected && !root.showSettings)
                Qt.quit();
            else if (!sock.connected)
                sock.connected = true;
        }
    }

    Socket {
        id: sock
        path: root.sockPath
        connected: true
        parser: SplitParser {
            splitMarker: "\n"
            onRead: data => root.handleLine(data)
        }
        onConnectionStateChanged: {
            if (!sock.connected) {
                if (root.showSettings)
                    reconnectTimer.start();
                else
                    Qt.quit();
            }
        }
    }

    // ---- Recording overlay: bottom-center, 300x56, no keyboard focus ----
    LazyLoader {
        active: root.state !== "IDLE" && !root.showSettings
        PanelWindow {
            id: overlay
            implicitWidth: 300
            implicitHeight: 56
            color: "transparent"
            // Anchor bottom-center, 24px above usable edge, no exclusive zone.
            anchors {
                bottom: true
                left: true
                right: true
            }
            margins {
                bottom: 24
            }
            WlrLayershell.exclusionMode: ExclusionMode.Ignore
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

            Rectangle {
                anchors.centerIn: parent
                width: 300
                // Grows by one line while provisional (unstable) text previews.
                height: root.provisional !== "" ? 88 : 56
                radius: 18
                color: "#17181D"
                border.color: "#2A2C36"
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 8
                    anchors.topMargin: 6
                    anchors.bottomMargin: 6
                    spacing: 2

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 8

                    // Live amplitude: 16 mini-bars, updates <=30 Hz.
                    Row {
                        spacing: 2
                        Repeater {
                            model: 16
                            Rectangle {
                                width: 3
                                height: {
                                    var v = root.ampHistory[root.ampHistory.length - 16 + index] || 0;
                                    return 4 + v * 20;
                                }
                                radius: 1.5
                                color: root.state === "ERROR" ? "#FF8C9B" : "#B9A3FF"
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }

                    ColumnLayout {
                        spacing: 0
                        Layout.fillWidth: true
                        Text {
                            text: stateLabel(root.state)
                            color: "#F5F5F7"
                            font.pixelSize: 13
                            font.bold: true
                            elide: Text.ElideRight
                        }
                        Text {
                            text: overlaySub()
                            color: "#B7BAC5"
                            font.pixelSize: 11
                            elide: Text.ElideRight
                        }
                    }

                    Button {
                        text: "■"
                        Accessible.name: "Stop dictation"
                        onClicked: root.send({
                            "op": "stop"
                        })
                    }
                    Button {
                        text: "✕"
                        Accessible.name: "Cancel dictation"
                        onClicked: root.send({
                            "op": "cancel"
                        })
                    }
                    }

                    // Live provisional tail: explicitly NOT inserted text.
                    // Only stabilized words (committedWords) reach the app.
                    Text {
                        visible: root.provisional !== ""
                        Layout.fillWidth: true
                        text: "…" + root.provisional + "  ·  " + root.committedWords + " typed"
                        color: "#FFD18A"
                        font.pixelSize: 11
                        font.italic: true
                        elide: Text.ElideLeft
                    }
                }
            }
        }
    }

    function stateLabel(s) {
        if (s === "STARTING")
            return "Starting microphone…";
        if (s === "RECORDING")
            return "Listening";
        if (s === "TRANSCRIBING")
            return "Transcribing…";
        if (s === "CLEANING")
            return "Cleaning up…";
        if (s === "READY")
            return "Text ready";
        if (s === "INSERTING")
            return "Text ready";
        if (s === "CANCELLED")
            return "Cancelled";
        if (s === "ERROR")
            return "Error";
        return "Idle";
    }

    function overlaySub() {
        var t = root.elapsedSecs + "s";
        if (root.statusText && root.statusText !== "")
            return t + " · " + root.statusText;
        return t;
    }

    // ---- Settings window (normal focusable window, insertion disabled) ----
    LazyLoader {
        active: root.showSettings
        FloatingWindow {
            id: settingsWin
            implicitWidth: 760
            implicitHeight: 560
            title: "Vaani Settings"
            visible: true
            color: "#1E1F26"
            onVisibleChanged: {
                if (!visible)
                    root.showSettings = false;
            }
            SettingsView {}
        }
    }
}
