// Vaani SettingsView: five pages, socket-driven (no polling loops).
// Reads config once via config_get on open; writes via validated config_set.
// One-shot mic-test / doctor requests only when the user presses the button.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: settingsRoot
    anchors.fill: parent
    spacing: 0

    property var cfg: ({})
    property string doctorText: ""
    property string micText: ""

    required property var bridge
    required property var colors
    Component.onCompleted: { bridge.settingsApi = settingsRoot; requestConfig(); }
    Component.onDestruction: { if (bridge.settingsApi === settingsRoot) bridge.settingsApi = null; }
    function requestConfig() { bridge.sendOp("config_get"); }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 104
        color: colors.surface
        Column {
            anchors.left: parent.left; anchors.leftMargin: 24
            anchors.verticalCenter: parent.verticalCenter; spacing: 6
            Label { text: "Vaani"; font.pixelSize: 30; font.weight: Font.DemiBold; color: colors.text }
            Label { text: "Your voice. Your device."; color: colors.muted }
        }
        Label { anchors.right: parent.right; anchors.rightMargin: 24; anchors.verticalCenter: parent.verticalCenter; text: colors.dynamic ? "●  Dynamic theme" : "●  Vaani theme"; color: colors.accent }
    }
    Label { Layout.fillWidth: true; Layout.leftMargin: 24; text: bridge.statusText; color: colors.muted; wrapMode: Text.WordWrap }
    function routeData(data) {
        if (data.key !== undefined) {
            requestConfig();
        } else if (data.general && data.recognition) {
            settingsRoot.cfg = data;
        } else if (data.checks) {
            settingsRoot.doctorText = JSON.stringify(data, null, 2);
        } else if (data.peak !== undefined) {
            var peak = Number(data.peak).toFixed(3);
            var rms = Number(data.rms).toFixed(3);
            settingsRoot.micText = "peak " + peak + " · rms " + rms + (Number(data.rms) > 0.02 ? " — level OK" : " — very quiet, check input gain / source");
        }
    }

    function setKey(key, value) {
        bridge.sendOp("config_set", {key: key, value: value});
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: 0
        Rectangle {
            Layout.preferredWidth: 170
            Layout.fillHeight: true
            color: colors.surface
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 6
                Repeater {
                    model: ["General", "Audio", "Recognition", "Shortcuts", "Privacy & diagnostics"]
                    delegate: Button {
                        required property int index
                        required property string modelData
                        Layout.fillWidth: true
                        text: modelData
                        highlighted: pages.currentIndex === index
                        onClicked: pages.currentIndex = index
                    }
                }
                Item { Layout.fillHeight: true }
                Label { text: "Private by default\nRuns on your device"; color: colors.muted; font.pixelSize: 11 }
            }
        }
    StackLayout {
        id: pages
        currentIndex: 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.margins: 16

        // ---- General ----
        ColumnLayout {
            spacing: 10
            Label {
                text: "Dictation profile"
                font.bold: true
            }
            ComboBox {
                model: ["economy"]
                currentIndex: Math.max(0, ["economy", "balanced", "ready"].indexOf(settingsRoot.cfg.general ? settingsRoot.cfg.general.residency_profile : "economy"))
                onActivated: settingsRoot.setKey("general.residency_profile", currentText)
            }
            Label {
                text: "The model unloads after each dictation. Balanced and Ready residency are not implemented yet."
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                color: colors.muted
            }
            CheckBox {
                text: "Review before insertion"
                checked: settingsRoot.cfg.general ? settingsRoot.cfg.general.review_before_insertion : false
                onToggled: settingsRoot.setKey("general.review_before_insertion", checked ? "true" : "false")
            }
        }

        // ---- Audio ----
        ColumnLayout {
            spacing: 10
            Label {
                text: "Input device (empty = PipeWire default source)"
                font.bold: true
            }
            TextField {
                Layout.fillWidth: true
                placeholderText: "e.g. alsa_input.usb-… (stable name, not numeric node id)"
                text: settingsRoot.cfg.audio ? settingsRoot.cfg.audio.device_selector : ""
                onEditingFinished: settingsRoot.setKey("audio.device_selector", text)
            }
            Label {
                text: "CPU worker threads (1–16, default 4)"
                font.bold: true
            }
            SpinBox {
                from: 1
                to: 16
                value: settingsRoot.cfg.audio ? settingsRoot.cfg.audio.worker_threads : 4
                onValueModified: settingsRoot.setKey("audio.worker_threads", String(value))
            }
            Button {
                text: "Test microphone (3 s)"
                onClicked: {
                    bridge.sendOp("mic_test", {
                            "secs": 3
                        });
                }
            }
            Label {
                text: settingsRoot.micText
                color: colors.muted
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        // ---- Recognition ----
        ColumnLayout {
            spacing: 10
            Label {
                text: "Recognition model"
                font.bold: true
            }
            ComboBox {
                model: ["tiny", "base", "base.en", "small"]
                currentIndex: Math.max(0, ["tiny", "base", "base.en", "small"].indexOf(settingsRoot.cfg.recognition ? settingsRoot.cfg.recognition.model : "base"))
                onActivated: settingsRoot.setKey("recognition.model", currentText)
            }
            Label {
                text: "Language (explicit setting; auto-detection fails on short utterances)"
                font.bold: true
            }
            ComboBox {
                model: ["en", "hi", "bn"]
                currentIndex: Math.max(0, ["en", "hi", "bn"].indexOf(settingsRoot.cfg.recognition ? settingsRoot.cfg.recognition.language : "en"))
                onActivated: settingsRoot.setKey("recognition.language", currentText)
            }
            Label {
                text: "Compute device (CPU default; CUDA needs a user-selected GPU build)"
                font.bold: true
            }
            ComboBox {
                model: ["cpu", "cuda"]
                currentIndex: (settingsRoot.cfg.recognition && settingsRoot.cfg.recognition.device === "cuda") ? 1 : 0
                onActivated: settingsRoot.setKey("recognition.device", currentText)
            }
            CheckBox {
                text: "Translate to English (opt-in)"
                checked: settingsRoot.cfg.recognition ? settingsRoot.cfg.recognition.translate_to_en : false
                onToggled: settingsRoot.setKey("recognition.translate_to_en", checked ? "true" : "false")
            }
        }

        // ---- Shortcuts ----
        ScrollView {
            ColumnLayout {
                width: parent.width
                spacing: 8
                Label {
                    text: "Defaults (Hyprland bindings invoke the CLI; no /dev/input listener)"
                    font.bold: true
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Label {
                    text: "Super+Alt+Space — toggle · Super+H — live dictation (types stabilized words as you speak) · Super+Alt+V — hold-to-talk · Super+Alt+Esc — cancel · Super+Alt+S — settings · Super+Alt+C — copy pending"
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                    color: colors.text
                }
                Label {
                    text: "Classic Hyprland: source the installed vaani.conf. Lua setups: use vaani.lua. Add only one set of shortcuts and check for conflicts in your compositor config."
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                    color: colors.muted
                }
            }
        }

        // ---- Privacy & Diagnostics ----
        ColumnLayout {
            spacing: 10
            CheckBox {
                text: "Transcript history (not implemented)"
                enabled: false
                checked: settingsRoot.cfg.privacy ? settingsRoot.cfg.privacy.save_history : false
                onToggled: settingsRoot.setKey("privacy.save_history", checked ? "true" : "false")
            }
            CheckBox {
                text: "Hide transcript previews (for screen sharing)"
                checked: settingsRoot.cfg.privacy ? settingsRoot.cfg.privacy.hide_preview_on_sharing : false
                onToggled: settingsRoot.setKey("privacy.hide_preview_on_sharing", checked ? "true" : "false")
            }
            Label {
                text: "Cleanup mode (raw is the dependable default)"
                font.bold: true
            }
            ComboBox {
                model: ["raw", "clean", "stream"]
                currentIndex: (settingsRoot.cfg.cleanup && settingsRoot.cfg.cleanup.mode === "clean") ? 1 : (settingsRoot.cfg.cleanup && settingsRoot.cfg.cleanup.mode === "stream") ? 2 : 0
                onActivated: settingsRoot.setKey("cleanup.mode", currentText)
            }
            TextField {
                Layout.fillWidth: true
                placeholderText: "Local cleanup endpoint, e.g. http://localhost:11434 (empty = disabled)"
                text: settingsRoot.cfg.cleanup ? settingsRoot.cfg.cleanup.endpoint : ""
                onEditingFinished: settingsRoot.setKey("cleanup.endpoint", text)
            }
            Button {
                text: "Run diagnostics"
                onClicked: {
                    bridge.sendOp("doctor");
                }
            }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                TextArea {
                    text: settingsRoot.doctorText
                    readOnly: true
                    wrapMode: Text.WordWrap
                    placeholderText: "Diagnostics appear here."
                }
            }
        }
    }
}

}
