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
    property bool showOnboarding: (Quickshell.env("VAANI_ONBOARDING") || "") === "1"
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
        // Keep the last live STT phrase visible while final transcription
        // completes. The overlay only renders daemon events; it never owns or
        // synthesizes any text delivery.
        if (root.state !== "RECORDING" && root.state !== "TRANSCRIBING") {
            root.provisional = "";
            root.liveWords = "";
        }
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
            implicitWidth: 440
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
                width: 440
                height: 72
                radius: 22
                color: "#19161C"
                border.color: "#19161C"
                border.width: 2
                opacity: root.dismissing ? 0 : 1
                transform: Translate {
                    y: root.dismissing ? card.height + 32 : 0
                    Behavior on y { NumberAnimation { duration: 320; easing.type: Easing.InCubic } }
                }
                Behavior on opacity { NumberAnimation { duration: 240 } }
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 13

                    // Same 44 px lilac activity mark as the brand-kit voice box.
                    Rectangle {
                        Layout.preferredWidth: 44
                        Layout.preferredHeight: 44
                        radius: 13
                        color: "#E8DCFF"
                        Item {
                            anchors.centerIn: parent
                            width: 25
                            height: 28
                            Row {
                                anchors.centerIn: parent
                                spacing: 4
                                Repeater {
                                    model: 5
                                    Rectangle {
                                        required property int index
                                        width: 3
                                        height: root.state === "RECORDING" ? Math.max(7, root.barH(index * 3)) : [10, 18, 25, 18, 10][index]
                                        anchors.verticalCenter: parent.verticalCenter
                                        radius: 2
                                        color: "#54296C"
                                        Behavior on height { NumberAnimation { duration: 90 } }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignVCenter
                        spacing: 2
                        Text {
                            text: root.state === "INSERTING" ? "TYPING CLEAN TEXT" : root.state === "CLEANING" ? "CLEANING TRANSCRIPT" : root.state === "TRANSCRIBING" ? "TRANSCRIBING" : root.state === "ERROR" ? "NEEDS ATTENTION" : "LISTENING"
                            color: "#CFC6D3"
                            font.pixelSize: 10
                            font.weight: Font.Bold
                            font.letterSpacing: 1
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        Text {
                            id: voiceLine
                            // Live words are supplied by daemon provisional events. This is
                            // deliberately presentation-only: no QML prediction or typing.
                            text: (root.state === "RECORDING" || root.state === "TRANSCRIBING") && root.liveWords !== "" ? root.liveWords : (root.statusText || "Speak naturally…")
                            textFormat: Text.PlainText
                            color: root.state === "ERROR" ? "#FFB4AB" : "#FDFBF8"
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                            onTextChanged: voiceLineFade.restart()
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 31
                        Layout.preferredHeight: 31
                        Layout.alignment: Qt.AlignVCenter
                        radius: 10
                        color: "#4A424E"
                        Rectangle {
                            anchors.centerIn: parent
                            width: 10
                            height: 10
                            radius: 2
                            color: "#FFD4A3"
                        }
                        MouseArea {
                            anchors.fill: parent
                            enabled: root.state === "RECORDING" || root.state === "STARTING"
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onClicked: root.sendOp("stop")
                        }
                    }
                }
                PropertyAnimation {
                    id: voiceLineFade
                    target: voiceLine
                    property: "opacity"
                    from: 0.35
                    to: 1
                    duration: 140
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
            Loader {
                anchors.fill: parent
                sourceComponent: root.showOnboarding ? onboardingComponent : settingsComponent
            }
        }
    }

    Component {
        id: onboardingComponent
        OnboardingView {
            bridge: root
            colors: theme
            onFinished: {
                root.showOnboarding = false;
                root.showSettings = false;
            }
        }
    }
    Component {
        id: settingsComponent
        SettingsView { bridge: root; colors: theme }
    }
}
