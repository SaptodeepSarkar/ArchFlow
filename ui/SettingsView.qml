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

    Component.onCompleted: {
        var p = parent;
        while (p && !p.send)
            p = p.parent;
        if (p) {
            p.settingsApi = settingsRoot;
            settingsRoot.requestConfig();
        }
    }

    function requestConfig() {
        // Ask the parent scope to send; parent exposes root.send().
        var p = parent;
        while (p && !p.send)
            p = p.parent;
        if (p)
            p.send({
                "op": "config_get"
            });
    }

    TabBar {
        id: tabs
        Layout.fillWidth: true
        TabButton {
            text: "General"
        }
        TabButton {
            text: "Audio"
        }
        TabButton {
            text: "Recognition"
        }
        TabButton {
            text: "Shortcuts"
        }
        TabButton {
            text: "Privacy & Diagnostics"
        }
    }

    function routeData(data) {
        if (data.general && data.recognition) {
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
        var p = parent;
        while (p && !p.send)
            p = p.parent;
        if (p)
            p.send({
                "op": "config_set",
                "args": {
                    "key": key,
                    "value": value
                }
            });
    }

    StackLayout {
        currentIndex: tabs.currentIndex
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
                model: ["economy", "balanced", "ready"]
                currentIndex: Math.max(0, ["economy", "balanced", "ready"].indexOf(settingsRoot.cfg.general ? settingsRoot.cfg.general.residency_profile : "economy"))
                onActivated: settingsRoot.setKey("general.residency_profile", currentText)
            }
            Label {
                text: "Unload after each dictation: saves memory; the next recording needs to load the model."
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
                color: "#B7BAC5"
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
                    var p = parent;
                    while (p && !p.send)
                        p = p.parent;
                    if (p)
                        p.send({
                            "op": "mic_test",
                            "args": {
                                "secs": 3
                            }
                        });
                }
            }
            Label {
                text: settingsRoot.micText
                color: "#B7BAC5"
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }

        // ---- Recognition ----
        ColumnLayout {
            spacing: 10
            Label {
                text: "Model (downloaded on first-run setup, never bundled)"
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
                    color: "#F5F5F7"
                }
                Label {
                    text: "Add 'source = ~/.config/hypr/vaani.conf' to hyprland.conf (app-owned include; never edits your config). Conflicts with your existing binds are reported by 'vaani doctor'."
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                    color: "#B7BAC5"
                }
            }
        }

        // ---- Privacy & Diagnostics ----
        ColumnLayout {
            spacing: 10
            CheckBox {
                text: "Save transcript history (off by default)"
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
                model: ["raw", "clean"]
                currentIndex: (settingsRoot.cfg.cleanup && settingsRoot.cfg.cleanup.mode === "clean") ? 1 : 0
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
                    var p = parent;
                    while (p && !p.send)
                        p = p.parent;
                    if (p)
                        p.send({
                            "op": "doctor"
                        });
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
