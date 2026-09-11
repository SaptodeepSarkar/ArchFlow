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

    property string sockPath: Quickshell.env("VAANI_SOCKET") || (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/vaani/control.sock"
    property string state: "IDLE"
    property string statusText: ""
    property real amplitude: 0
    property var ampHistory: []
    property bool showSettings: (Quickshell.env("VAANI_OPEN_SETTINGS") || "") === "1"
    property string pendingText: ""
    property var settingsApi: null
    property string provisional: ""
    property bool firstLine: true
    property string sessionId: ""
    property string lastWord: ""
    property string nextWord: ""
    property bool dismissing: false
    // Set when the finished session copied its transcript to the clipboard:
    // the "Copied to clipboard" popup lingers long enough to be read.
    property bool copiedNotice: false
    Theme { id: theme }

    // Daemon wire format: {protocol_version, request_id, session_id, kind}
    // where kind = {op, args?}. Anything else is rejected as malformed.
    function sendOp(op, args) {
        if (!sock.connected) { root.statusText = "Daemon unavailable — start vaanid.service"; return; }
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
        if (msg.event && msg.session_id && root.sessionId && msg.session_id !== root.sessionId && msg.event !== "state")
            return;
        if (msg.event === "state" || (msg.state && !msg.event && msg.ok === undefined)) {
            applyState(msg);
            return;
        }
        if (msg.event === "provisional") {
            var tail = (msg.data && msg.data.tail) || "";
            var hidden = msg.data && msg.data.hidden;
            root.provisional = hidden ? "" : String(tail);
            root.lastWord = hidden ? "" : ((msg.data && msg.data.last_word) || "");
            root.nextWord = hidden ? "" : ((msg.data && msg.data.next_word) || "");
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
        // A clipboard confirmation lingers longer so it can be read.
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
                if (msg.data.copied === true)
                    root.copiedNotice = true;
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
        var previous = root.state;
        if (msg.session_id) root.sessionId = msg.session_id;
        if (msg.state)
            root.state = msg.state;
        if (msg.message)
            root.statusText = msg.message;
        if (msg.data && msg.data.text !== undefined)
            root.pendingText = msg.data.text;
        if (msg.data && msg.data.copied === true)
            root.copiedNotice = true;
        if (root.state === "RECORDING") {
            root.dismissing = false;
            root.copiedNotice = false;
            closeTimer.stop();
            if (previous !== "RECORDING") {
                root.provisional = "";
                root.lastWord = ""; root.nextWord = "";
                root.ampHistory = [];
            }
        }
        if (root.state !== "RECORDING") { root.provisional = ""; root.lastWord = ""; root.nextWord = ""; }
        root.checkFinished();
    }

    // On-demand UI residency: linger briefly on finished states so the
    // outcome ("Pasted", "On clipboard", errors) is visible, then exit.
    // READY is finished too: the daemon never parks there, but an old or
    // racing event must not stick the overlay on "Text ready" forever.
    function checkFinished() {
        if (root.showSettings)
            return;
        if (root.state === "IDLE" || root.state === "CANCELLED" || root.state === "READY") {
            root.dismissing = true;
            closeTimer.restart();
        } else if (root.state === "ERROR") {
            root.dismissing = false;
            closeTimer.restart();
        } else {
            root.dismissing = false;
            closeTimer.stop();
        }
    }

    Timer {
        id: closeTimer
        interval: root.state === "ERROR" ? 1600 : root.copiedNotice ? 2200 : 360
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
            if (sock.connected) {
                root.firstLine = true;
                if (root.settingsApi) root.settingsApi.requestConfig();
            } else {
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
        active: (root.state !== "IDLE" || closeTimer.running) && !root.showSettings
        PanelWindow {
            id: overlay
            implicitWidth: 320
            implicitHeight: card.height + 48
            color: "transparent"
            // Anchor bottom-center, 24px above usable edge, no exclusive zone.
            anchors {
                bottom: true
            }
            margins {
                bottom: 24
            }
            WlrLayershell.exclusionMode: ExclusionMode.Ignore
            WlrLayershell.layer: WlrLayer.Overlay
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

            Rectangle {
                id: card
                anchors.centerIn: parent
                width: 320
                height: 88
                radius: 18
                color: theme.surface
                border.color: theme.outline
                opacity: root.dismissing ? 0 : 1
                transform: Translate {
                    y: root.dismissing ? card.height + 32 : 0
                    Behavior on y { NumberAnimation { duration: 320; easing.type: Easing.InCubic } }
                }
                Behavior on opacity { NumberAnimation { duration: 240 } }
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 28
                        Row {
                            anchors.centerIn: parent
                            spacing: 6
                            Repeater {
                                model: 16
                                Rectangle {
                                    required property int index
                                    width: 4
                                    height: root.state === "RECORDING" ? root.barH(index) : 3
                                    anchors.verticalCenter: parent.verticalCenter
                                    radius: 2
                                    color: root.state === "ERROR" ? theme.error : theme.accent
                                }
                            }
                        }
                    }
                    RowLayout {
                        visible: root.lastWord !== "" || root.nextWord !== ""
                        Layout.fillWidth: true
                        spacing: 12
                        Text { text: root.lastWord; textFormat: Text.PlainText; color: theme.text; font.pixelSize: 18; font.weight: Font.DemiBold; elide: Text.ElideLeft; Layout.maximumWidth: 140 }
                        Text { text: root.nextWord; textFormat: Text.PlainText; color: theme.accent; opacity: 0.72; font.pixelSize: 18; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                    Text {
                        visible: root.lastWord === "" && root.nextWord === ""
                        text: root.statusText || "Speak naturally…"
                        textFormat: Text.PlainText
                        color: root.state === "ERROR" ? theme.error : theme.text
                        font.pixelSize: 13
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        Layout.fillWidth: true
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
            color: theme.background
            onVisibleChanged: {
                if (!visible)
                    { root.showSettings = false; root.checkFinished(); }
            }
            SettingsView {
                bridge: root
                colors: theme
            }
        }
    }
}
