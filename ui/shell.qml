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
    property bool showSettings: (Quickshell.env("VAANI_OPEN_SETTINGS") || "") === "1"
    property string pendingText: ""
    property var settingsApi: null
    property string provisional: ""
    property bool firstLine: true

    // Daemon wire format: {protocol_version, request_id, session_id, kind}
    // where kind = {op, args?}. Anything else is rejected as malformed.
    function sendOp(op, args) {
        var msg = {
            protocol_version: 1,
            request_id: "qml-" + Math.floor(Math.random() * 1e9),
            session_id: null,
            kind: {
                op: op
            }
        };
        if (args !== undefined)
            msg.kind.args = args;
        sock.write(JSON.stringify(msg) + "\n");
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
        // A stale overlay that connects to an already-idle daemon exits now.
        if (root.firstLine) {
            root.firstLine = false;
            if ((msg.state === "IDLE" || msg.state === "CANCELLED" || !msg.state) && !root.showSettings && !msg.event) {
                Qt.quit();
                return;
            }
        }
        if (msg.event === "state" || (msg.state && !msg.event && !msg.ok && msg.event !== undefined)) {
            applyState(msg);
            return;
        }
        if (msg.event === "provisional") {
            var tail = (msg.data && msg.data.tail) || "";
            var hidden = msg.data && msg.data.hidden;
            root.provisional = hidden ? "" : String(tail).slice(-160);
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
        // Responses carry ok/state/message/data. Finished states linger
        // briefly so the outcome is visible, then the overlay exits.
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
            root.checkFinished();
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
            closeTimer.stop();
            if (msg.event === "state") {
                root.provisional = "";
                root.ampHistory = [];
            }
        }
        root.checkFinished();
    }

    // On-demand UI residency: linger 1.6 s on finished states so the outcome
    // ("Pasted", "On clipboard", errors) is visible, then exit.
    function checkFinished() {
        if (root.showSettings)
            return;
        if (root.state === "IDLE" || root.state === "CANCELLED" || root.state === "ERROR")
            closeTimer.restart();
        else
            closeTimer.stop();
    }

    Timer {
        id: closeTimer
        interval: 1600
        repeat: false
        onTriggered: {
            if (!root.showSettings)
                Qt.quit();
        }
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

    // Bar height for visualizer slot i (0..15), visibility-scaled so quiet
    // mics still move. Updates arrive <=30 Hz while recording only.
    function barH(i) {
        var v = root.ampHistory[root.ampHistory.length - 16 + i] || 0;
        v = Math.min(1, v * 6);
        return 3 + 25 * Math.pow(v, 0.6);
    }

    // ---- Recording overlay: bottom-center, no keyboard focus ----
    LazyLoader {
        active: root.state !== "IDLE" && !root.showSettings
        PanelWindow {
            id: overlay
            implicitWidth: 320
            implicitHeight: card.height + 48
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

            // Minimal card: wave strip + live transcription only.
            // No buttons (SUPER+H toggles), no state chrome. Outcome text
            // lingers ~1.6 s after finish, then the process exits.
            Rectangle {
                id: card
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                width: 320
                height: words.text !== "" ? 92 : 52
                radius: 18
                color: "#17181D"
                border.color: "#2A2C36"
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 14
                    anchors.rightMargin: 14
                    anchors.topMargin: 9
                    anchors.bottomMargin: 9
                    spacing: 6

                    // Wave: full-width strip, bars bottom-up.
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 26
                        Repeater {
                            model: 16
                            Rectangle {
                                x: index * 18.5
                                y: parent.height - height
                                width: 10
                                height: root.barH(index)
                                radius: 2
                                color: root.state === "ERROR" ? "#FF8C9B" : "#B9A3FF"
                            }
                        }
                    }

                    // Word-by-word live transcription (provisional tail while
                    // recording; outcome / error text after finish).
                    Text {
                        id: words
                        visible: text !== ""
                        Layout.fillWidth: true
                        text: root.provisional !== "" ? root.provisional : root.statusText
                        color: root.state === "ERROR" ? "#FF8C9B" : (root.provisional !== "" ? "#F5F5F7" : "#B7BAC5")
                        font.pixelSize: 12
                        font.italic: root.provisional !== ""
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                        elide: Text.ElideRight
                    }
                }
            }
        }
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
