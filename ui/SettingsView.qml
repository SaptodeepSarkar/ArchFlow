// Vaani desktop control surface. The visual tokens mirror brand/brand-kit.html:
// warm paper, ink, plum intent, lilac actions, and apricot feature cards.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell.Io

Rectangle {
    id: app
    anchors.fill: parent
    color: "#FDFBF8"
    required property var bridge
    required property var colors
    property var cfg: ({})
    property int page: 0
    property string doctorText: ""
    property string micText: ""
    property string accountText: "Local only"
    property bool serviceActive: false
    property bool serviceEnabled: false
    property string serviceMessage: "Checking the Vaani service…"
    property string pendingServiceAction: ""
    signal replayWelcome()

    Component.onCompleted: { bridge.settingsApi = app; requestConfig(); refreshService(); }
    Component.onDestruction: if (bridge.settingsApi === app) bridge.settingsApi = null
    function requestConfig() { bridge.sendOp("config_get"); }
    function setKey(key, value) { bridge.sendOp("config_set", {key: key, value: value}); }
    function saveShortcut(value) {
        var trimmed = value.trim();
        if (trimmed.length === 0) {
            serviceMessage = "Enter a shortcut such as SUPER+H.";
            return;
        }
        pendingServiceAction = "shortcut";
        serviceMessage = "Saving shortcut and reloading Hyprland…";
        shortcutWriter.exec(["vaani-desktop", "shortcut", trimmed]);
    }
    function refreshService() {
        if (!serviceProbe.running)
            serviceProbe.exec(["systemctl", "--user", "is-active", "--quiet", "vaanid.service"]);
        if (!bootProbe.running)
            bootProbe.exec(["systemctl", "--user", "is-enabled", "--quiet", "vaanid.service"]);
    }
    function manageService(action) {
        pendingServiceAction = action;
        serviceMessage = (action === "start" ? "Starting" : action === "stop" ? "Stopping" : action === "enable" ? "Enabling start at login" : "Disabling start at login") + "…";
        serviceCommand.exec(["systemctl", "--user", action, "vaanid.service"]);
    }
    function routeData(data) {
        if (data.key !== undefined) requestConfig();
        else if (data.general && data.recognition) cfg = data;
        else if (data.checks) doctorText = JSON.stringify(data, null, 2);
        else if (data.peak !== undefined) micText = "peak " + Number(data.peak).toFixed(3) + " · rms " + Number(data.rms).toFixed(3) + (Number(data.rms) > 0.02 ? " — ready" : " — very quiet");
    }
    function addVocabulary(value) { if (value.trim().length > 0) { setKey("cleanup.vocabulary", value.trim()); requestConfig(); } }

    Timer {
        id: serviceRefreshTimer
        interval: 350
        repeat: false
        onTriggered: app.refreshService()
    }
    Process {
        id: serviceProbe
        onExited: function(exitCode) {
            app.serviceActive = exitCode === 0;
            if (!serviceCommand.running && !shortcutWriter.running)
                app.serviceMessage = app.serviceActive ? "Vaani is listening for your shortcut." : "Vaani is stopped. Start it here when you are ready.";
        }
    }
    Process {
        id: bootProbe
        onExited: function(exitCode) { app.serviceEnabled = exitCode === 0; }
    }
    Process {
        id: serviceCommand
        onExited: function(exitCode) {
            var verb = app.pendingServiceAction;
            app.serviceMessage = exitCode === 0
                ? (verb === "start" ? "Vaani started." : verb === "stop" ? "Vaani stopped." : verb === "enable" ? "Vaani will start when you log in." : "Vaani will not start automatically.")
                : "That service change failed. Check the systemd user session.";
            serviceRefreshTimer.restart();
        }
    }
    Process {
        id: shortcutWriter
        onExited: function(exitCode) {
            app.serviceMessage = exitCode === 0
                ? "Shortcut saved and Hyprland reload requested."
                : "Shortcut was not saved. Use a supported chord such as SUPER+H.";
            app.requestConfig();
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Rectangle {
            Layout.preferredWidth: 204
            Layout.fillHeight: true
            color: "#FFFDFB"
            border.color: "#E8E2E7"
            border.width: 1
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 18; spacing: 8
                RowLayout {
                    Layout.fillWidth: true; spacing: 9
                    VaaniMark { markSize: 31; dark: false }
                }
                Label { text: "Your voice. Your device."; color: "#827B87"; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                Item { Layout.preferredHeight: 16 }
                Repeater {
                    model: ["Home", "Personalize", "Settings", "Account"]
                    delegate: VaaniButton {
                        required property int index
                        required property string modelData
                        Layout.fillWidth: true; text: modelData; tone: app.page === index ? "primary" : "text"
                        onClicked: app.page = index
                    }
                }
                Item { Layout.fillHeight: true }
                Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#E8E2E7" }
                Label { text: "LOCAL-FIRST"; color: "#6B3A85"; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.2 }
                Label { text: "Audio and raw dictation stay on this device."; color: "#827B87"; font.pixelSize: 11; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
        }
        ColumnLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0
            Rectangle {
                Layout.fillWidth: true; Layout.preferredHeight: 76; color: "#FDFBF8"
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 32; anchors.rightMargin: 28
                    Label { text: ["Good morning, speak freely.", "Make Vaani sound like you.", "Tune Vaani to your workflow.", "Sync only what you choose."][app.page]; color: "#19161C"; font.pixelSize: 23; font.bold: true; Layout.fillWidth: true }
                    Rectangle { implicitWidth: 86; implicitHeight: 31; radius: 16; color: "#FFF0DF"; Label { anchors.centerIn: parent; text: "●  LOCAL"; color: "#54296C"; font.pixelSize: 10; font.bold: true } }
                }
            }
            Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#E8E2E7" }
            StackLayout {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.margins: 32; currentIndex: app.page

                Flickable {
                    contentWidth: width; contentHeight: homeColumn.implicitHeight; clip: true
                    ColumnLayout { id: homeColumn; width: parent.width; spacing: 18
                        Rectangle { Layout.fillWidth: true; implicitHeight: 252; radius: 28; color: "#FFD4A3"
                            ColumnLayout { anchors.fill: parent; anchors.margins: 28; spacing: 10
                                Label { text: "VOICE, WITHOUT THE FRICTION"; color: "#6B3A85"; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.4 }
                                Label { text: "Speak.\nVaani writes."; color: "#19161C"; font.pixelSize: 34; font.bold: true; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                Label { text: "Press " + (app.cfg.general ? app.cfg.general.shortcut : "SUPER+H") + " anywhere to start dictating."; color: "#57505C"; font.pixelSize: 14 }
                                VaaniButton { text: "Replay welcome"; tone: "secondary"; onClicked: app.replayWelcome() }
                            }
                        }
                        RowLayout { Layout.fillWidth: true; spacing: 14
                            Rectangle { Layout.fillWidth: true; implicitHeight: 116; radius: 20; color: "#FFFDFB"; border.color: "#E8E2E7"
                                Column { anchors.fill: parent; anchors.margins: 18; spacing: 6
                                    Label { text: "Shortcut"; color: "#827B87"; font.pixelSize: 11; font.bold: true }
                                    Label { text: app.cfg.general ? app.cfg.general.shortcut : "SUPER+H"; color: "#19161C"; font.pixelSize: 19; font.bold: true }
                                    Label { text: "Change in Settings"; color: "#6B3A85"; font.pixelSize: 11 }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; implicitHeight: 116; radius: 20; color: "#FFFDFB"; border.color: "#E8E2E7"
                                Column { anchors.fill: parent; anchors.margins: 18; spacing: 6
                                    Label { text: "Model"; color: "#827B87"; font.pixelSize: 11; font.bold: true }
                                    Label { text: app.cfg.recognition ? app.cfg.recognition.model : "base"; color: "#19161C"; font.pixelSize: 19; font.bold: true }
                                    Label { text: app.cfg.general ? app.cfg.general.residency_profile : "economy"; color: "#6B3A85"; font.pixelSize: 11 }
                                }
                            }
                        }
                        Label { text: "Personal vocabulary"; color: "#19161C"; font.pixelSize: 17; font.bold: true }
                        Label { text: app.cfg.cleanup && app.cfg.cleanup.vocabulary && app.cfg.cleanup.vocabulary.length ? app.cfg.cleanup.vocabulary.join("  ·  ") : "No words added yet — add names and technical terms in Personalize."; color: "#827B87"; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }

                Flickable {
                    contentWidth: width; contentHeight: personalizeColumn.implicitHeight; clip: true
                    ColumnLayout { id: personalizeColumn; width: parent.width; spacing: 18
                        Label { text: "Your words, recognised properly."; color: "#19161C"; font.pixelSize: 30; font.bold: true; Layout.fillWidth: true }
                        Label { text: "Names, places, products, and technical terms are used as recognition context. They never become dictation history."; color: "#827B87"; font.pixelSize: 14; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 132; radius: 24; color: "#E8DCFF"
                            ColumnLayout { anchors.fill: parent; anchors.margins: 22; spacing: 10
                                Label { text: "PERSONAL VOCABULARY"; color: "#54296C"; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.3 }
                                RowLayout { Layout.fillWidth: true
                                    VaaniField { id: vocab; Layout.fillWidth: true; placeholderText: "Add a word or name" }
                                    VaaniButton { text: "Add word"; onClicked: { app.addVocabulary(vocab.text); vocab.text = "" } }
                                }
                            }
                        }
                        Label { text: app.cfg.cleanup && app.cfg.cleanup.vocabulary ? app.cfg.cleanup.vocabulary.join("  ·  ") : ""; color: "#57505C"; font.pixelSize: 15; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    }
                }

                Flickable {
                    contentWidth: width; contentHeight: settingsColumn.implicitHeight; clip: true
                    ColumnLayout { id: settingsColumn; width: parent.width; spacing: 15
                        Label { text: "Settings"; color: "#19161C"; font.pixelSize: 30; font.bold: true }
                        Label { text: "Make the tradeoffs visible. Vaani never changes these silently."; color: "#827B87"; font.pixelSize: 14 }
                        Label { text: "Primary shortcut"; color: "#19161C"; font.bold: true }
                        RowLayout { Layout.fillWidth: true
                            VaaniField { id: shortcut; Layout.fillWidth: true; text: app.cfg.general ? app.cfg.general.shortcut : "SUPER+H"; placeholderText: "SUPER+H" }
                            VaaniButton { text: "Save shortcut"; enabled: !shortcutWriter.running; onClicked: app.saveShortcut(shortcut.text) }
                        }
                        Label { text: "This updates Vaani’s app-owned Hyprland include and asks Hyprland to reload it."; color: "#827B87"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Label { text: "Model residency"; color: "#19161C"; font.bold: true }
                        RowLayout { Layout.fillWidth: true; spacing: 10; Repeater { model: ["economy", "balanced", "ready"]; delegate: VaaniButton { required property string modelData; Layout.fillWidth: true; text: modelData; tone: app.cfg.general && app.cfg.general.residency_profile === modelData ? "primary" : "secondary"; onClicked: app.setKey("general.residency_profile", modelData) } } }
                        Label { text: "Economy unloads after each dictation. Balanced keeps the model warm briefly. Ready keeps it resident longer."; color: "#827B87"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        RowLayout { Layout.fillWidth: true; spacing: 14
                            ColumnLayout { Layout.fillWidth: true
                                Label { text: "Final model"; color: "#19161C"; font.bold: true }
                                VaaniSelect { Layout.fillWidth: true; values: ["tiny", "base", "base.en", "small", "cozy", "v5"]; currentIndex: Math.max(0, values.indexOf(app.cfg.recognition ? app.cfg.recognition.model : "base")); onValueSelected: value => app.setKey("recognition.model", value) }
                            }
                            ColumnLayout { Layout.fillWidth: true
                                Label { text: "Language"; color: "#19161C"; font.bold: true }
                                VaaniSelect { Layout.fillWidth: true; values: ["en", "hi", "bn"]; currentIndex: Math.max(0, values.indexOf(app.cfg.recognition ? app.cfg.recognition.language : "en")); onValueSelected: value => app.setKey("recognition.language", value) }
                            }
                        }
                        Label { text: "Inference sidecar idle seconds"; color: "#19161C"; font.bold: true }
                        SpinBox { from: 0; to: 600; value: app.cfg.recognition ? app.cfg.recognition.server_idle_secs : 0; onValueModified: app.setKey("recognition.server_idle_secs", String(value)) }
                        VaaniButton { text: "Test microphone"; onClicked: bridge.sendOp("mic_test", {secs: 3}) }
                        Label { text: app.micText; color: "#6B3A85"; font.pixelSize: 12 }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: "#E8E2E7"; Layout.topMargin: 8; Layout.bottomMargin: 4 }
                        Label { text: "Vaani service"; color: "#19161C"; font.pixelSize: 18; font.bold: true }
                        Label { text: "This is the user service that receives " + (app.cfg.general ? app.cfg.general.shortcut : "SUPER+H") + "."; color: "#827B87"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 106; radius: 20; color: "#FFFDFB"; border.width: 1; border.color: "#E8E2E7"
                            ColumnLayout { anchors.fill: parent; anchors.margins: 16; spacing: 9
                                RowLayout { Layout.fillWidth: true
                                    Label { text: app.serviceActive ? "●  Running" : "●  Stopped"; color: app.serviceActive ? "#22755E" : "#827B87"; font.bold: true; Layout.fillWidth: true }
                                    VaaniButton { text: app.serviceActive ? "Stop service" : "Start service"; tone: app.serviceActive ? "secondary" : "primary"; enabled: !serviceCommand.running; onClicked: app.manageService(app.serviceActive ? "stop" : "start") }
                                }
                                Label { text: app.serviceMessage; color: "#57505C"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                            }
                        }
                        VaaniToggle {
                            title: "Start Vaani at login"
                            description: "Keeps the shortcut service ready after you sign in to your graphical session."
                            checked: app.serviceEnabled
                            busy: serviceCommand.running
                            onRequested: checked => app.manageService(checked ? "enable" : "disable")
                        }
                    }
                }

                Flickable {
                    contentWidth: width; contentHeight: accountColumn.implicitHeight; clip: true
                    ColumnLayout { id: accountColumn; width: parent.width; spacing: 18
                        Label { text: "Your Vaani account"; color: "#19161C"; font.pixelSize: 30; font.bold: true }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 142; radius: 24; color: "#FFD4A3"
                            Column { anchors.fill: parent; anchors.margins: 22; spacing: 8
                                Label { text: "OPTIONAL SYNC"; color: "#6B3A85"; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.3 }
                                Label { text: "Keep your words close."; color: "#19161C"; font.pixelSize: 24; font.bold: true }
                                Label { text: "Only vocabulary, snippets, and replacements sync. Audio and raw dictation never leave this device."; color: "#57505C"; wrapMode: Text.WordWrap; width: parent.width }
                            }
                        }
                        Label { text: "Use the secure desktop account command when you want sync:"; color: "#827B87"; font.pixelSize: 14 }
                        Rectangle { Layout.fillWidth: true; implicitHeight: 52; radius: 16; color: "#19161C"; Label { anchors.centerIn: parent; text: "vaani-desktop login"; color: "#FDFBF8"; font.family: "monospace"; font.pixelSize: 14 } }
                        Label { text: "Account status: " + app.accountText; color: "#6B3A85"; font.bold: true }
                    }
                }
            }
        }
    }
}
