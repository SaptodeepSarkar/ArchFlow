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
    property string liveWords: ""
    property string ctxWords: ""
    property string curWord: ""
    property bool firstLine: true
    property string sessionId: ""
    property bool dismissing: false
    // Set when the finished session copied its transcript to the clipboard:
    // the "Copied to clipboard" popup lingers long enough to be read.
    property bool copiedNotice: false
    Theme { id: theme }

    // Split the running preview into trailing context (dim) and the
    // current newest word (highlighted), so the speaker sees their place.
    onLiveWordsChanged: {
        var parts = String(root.liveWords).split(/\s+/).filter(function (w) { return w.length > 0; });
        if (parts.length === 0) {
            root.ctxWords = "";
            root.curWord = "";
        } else {
            root.curWord = parts[parts.length - 1];
            root.ctxWords = parts.slice(0, parts.length - 1).join(" ");
        }
    }

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
            var words = (msg.data && msg.data.words) || tail;
            root.liveWords = hidden ? "" : String(words);
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
                root.liveWords = "";
                root.ampHistory = [];
            }
        }
        if (root.state !== "RECORDING") { root.provisional = ""; root.liveWords = ""; }
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
            implicitWidth: 360
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
                width: 360
                height: 112
                radius: 18
                color: theme.surface
                border.color: theme.outline
                border.width: 1
                opacity: root.dismissing ? 0 : 1
                transform: Translate {
                    y: root.dismissing ? card.height + 32 : 0
                    Behavior on y { NumberAnimation { duration: 320; easing.type: Easing.InCubic } }
                }
                Behavior on opacity { NumberAnimation { duration: 240 } }
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 7
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 18
                        spacing: 7
                        Rectangle {
                            Layout.preferredWidth: 8
                            Layout.preferredHeight: 8
                            radius: 4
                            color: root.state === "ERROR" ? theme.error : theme.accent
                        }
                        Text {
                            Layout.fillWidth: true
                            text: root.state === "INSERTING" ? "Typing cleaned text" : root.state === "CLEANING" ? "Cleaning transcript" : root.state === "TRANSCRIBING" ? "Transcribing" : "Listening"
                            color: theme.text
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            text: root.state === "RECORDING" ? "SUPER+J copy" : ""
                            color: theme.muted
                            font.pixelSize: 10
                            opacity: 0.8
                        }
                    }
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 25
                        Row {
                            anchors.centerIn: parent
                            spacing: 5
                            Repeater {
                                model: 16
                                Rectangle {
                                    required property int index
                                width: 3
                                    height: root.state === "RECORDING" ? root.barH(index) : 3
                                    anchors.verticalCenter: parent.verticalCenter
                                    radius: 2
                                    color: root.state === "ERROR" ? theme.error : theme.accent
                                }
                            }
                        }
                    }
                    Row {
                        visible: root.liveWords !== ""
                        Layout.alignment: Qt.AlignHCenter
                        spacing: 6
                        Text {
                            text: root.ctxWords
                            textFormat: Text.PlainText
                            color: theme.text
                            opacity: 0.55
                            font.pixelSize: 16
                            elide: Text.ElideLeft
                            horizontalAlignment: Text.AlignRight
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(implicitWidth, 190)
                        }
                        Text {
                            id: curWordText
                            text: root.curWord
                            textFormat: Text.PlainText
                            color: theme.accent
                            font.pixelSize: 18
                            font.weight: Font.Bold
                            elide: Text.ElideRight
                            horizontalAlignment: Text.AlignLeft
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.min(implicitWidth, 120)
                            // The current word pops on arrival.
                            onTextChanged: liveFadeAnim.restart()
                        }
                    }
                    Text {
                        visible: root.liveWords === ""
                        text: root.statusText || "Speak naturally…"
                        textFormat: Text.PlainText
                        color: root.state === "ERROR" ? theme.error : theme.text
                        font.pixelSize: 12
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
                // Word-transition animation (non-visual, never laid out).
                PropertyAnimation {
                    id: liveFadeAnim
                    target: curWordText
                    property: "opacity"
                    from: 0
                    to: 1
                    duration: 160
                }
            }
        }
    }

    // Pointer/touch safety curtain during final delivery. It deliberately
    // keeps keyboardFocus None: wtype must continue targeting the original
    // focused application. Hyprland has no supported user-level global
    // physical-keyboard freeze that can coexist with virtual-keyboard output.
    PanelWindow {
        visible: root.state === "INSERTING" && !root.showSettings
        implicitWidth: screen ? screen.width : 1
        implicitHeight: screen ? screen.height : 1
        color: "transparent"
        anchors { top: true; bottom: true; left: true; right: true }
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.exclusionMode: ExclusionMode.Ignore
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            preventStealing: true
            hoverEnabled: true
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
