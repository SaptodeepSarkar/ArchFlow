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

            Rectangle {
                id: card
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                width: 320
                // Grows by one line while provisional (unstable) text previews.
                height: root.provisional !== "" ? 88 : 58
                radius: 18
                color: "#17181D"
                border.color: "#2A2C36"
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 10
                    anchors.topMargin: 7
                    anchors.bottomMargin: 7
                    spacing: 3

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 30
                        spacing: 8

                        // Visualizer: fixed box, manually placed bars bottom-up.
                        Item {
                            Layout.preferredWidth: 80
                            Layout.preferredHeight: 30
                            Layout.alignment: Qt.AlignVCenter
                            Repeater {
                                model: 16
                                Rectangle {
                                    x: index * 5
                                    y: parent.height - height
                                    width: 3
                                    height: root.barH(index)
                                    radius: 1.5
                                    color: root.state === "ERROR" ? "#FF8C9B" : "#B9A3FF"
                                }
                            }
                        }

                        ColumnLayout {
                            spacing: 1
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter
                            Text {
                                text: stateLabel(root.state)
                                color: "#F5F5F7"
                                font.pixelSize: 13
                                font.bold: true
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            Text {
                                text: overlaySub()
                                color: "#B7BAC5"
                                font.pixelSize: 11
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }

                        // Compact round buttons that always fit the 58px card.
                        Rectangle {
                            Layout.preferredWidth: 30
                            Layout.preferredHeight: 30
                            Layout.alignment: Qt.AlignVCenter
                            radius: 15
                            color: stopArea.containsMouse ? "#3A3D4A" : "#26282F"
                            Text {
                                anchors.centerIn: parent
                                text: "■"
                                color: "#F5F5F7"
                                font.pixelSize: 11
                            }
                            MouseArea {
                                id: stopArea
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: root.sendOp("stop")
                            }
                            Accessible.role: Accessible.Button
                            Accessible.name: "Stop dictation"
                        }
                        Rectangle {
                            Layout.preferredWidth: 30
                            Layout.preferredHeight: 30
                            Layout.alignment: Qt.AlignVCenter
                            radius: 15
                            color: cancelArea.containsMouse ? "#4A2E36" : "#26282F"
                            Text {
                                anchors.centerIn: parent
                                text: "✕"
                                color: "#FF8C9B"
                                font.pixelSize: 11
                            }
                            MouseArea {
                                id: cancelArea
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: root.sendOp("cancel")
                            }
                            Accessible.role: Accessible.Button
                            Accessible.name: "Cancel dictation"
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
