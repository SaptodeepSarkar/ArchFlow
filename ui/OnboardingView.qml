// First-run desktop setup. It mirrors the Android narrative, while exposing
// Linux-only controls before the user reaches the full settings surface.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: page
    anchors.fill: parent
    anchors.margins: 34
    spacing: 18

    required property var bridge
    required property var colors
    property var cfg: ({})
    property int step: 0
    property string micText: ""
    property string vocabularyText: ""
    signal finished()

    Component.onCompleted: { bridge.settingsApi = page; bridge.sendOp("config_get"); }
    Component.onDestruction: if (bridge.settingsApi === page) bridge.settingsApi = null

    function routeData(data) {
        if (data.general && data.recognition) cfg = data;
        if (data.peak !== undefined) {
            micText = "peak " + Number(data.peak).toFixed(3) + " · rms " + Number(data.rms).toFixed(3)
                + (Number(data.rms) > 0.02 ? " — microphone ready" : " — very quiet; check the selected source");
        }
    }
    function config(key, value) { bridge.sendOp("config_set", {key: key, value: value}); }

    Label { text: "VAANI SETUP"; color: colors.accent; font.pixelSize: 11; font.bold: true; font.letterSpacing: 1.4 }
    Label { text: ["A private voice tool for Linux", "Choose how Vaani works for you", "Check your microphone", "Teach Vaani your words", "Ready when you are"][page.step]; color: colors.text; font.family: "Georgia"; font.pixelSize: 38; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    Label { text: ["Speak in any focused text field, with the same local-first promise as the Android app.", "Use Vaani locally without an account, or connect later to sync vocabulary, snippets, and replacements.", "The test records only for this check and does not save audio.", "Add names, products, places, and technical terms exactly as you want them recognised.", "You can change every choice later in Settings."][page.step]; color: colors.muted; font.pixelSize: 15; wrapMode: Text.WordWrap; Layout.fillWidth: true }

    Item { Layout.fillHeight: true }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 12
        visible: page.step === 1
        Label { text: "Account is optional"; color: colors.text; font.bold: true }
        Label { text: "Local mode is ready immediately. Sign in later with `vaani-desktop login` to sync only your personalization records; recordings and raw dictation stay local."; color: colors.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        VaaniButton { text: "Continue with local mode"; onClicked: page.step++ }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 12
        visible: page.step === 2
        VaaniButton { text: "Test microphone (3 s)"; onClicked: bridge.sendOp("mic_test", {secs: 3}) }
        Label { text: page.micText; color: colors.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 12
        visible: page.step === 3
        Label { text: "Personal vocabulary"; color: colors.text; font.bold: true }
        RowLayout {
            Layout.fillWidth: true
            VaaniField { id: vocabulary; Layout.fillWidth: true; placeholderText: "e.g. ArchFlow, Quickshell, Saptodeep"; onAccepted: addVocabulary() }
            VaaniButton { text: "Add"; onClicked: addVocabulary() }
        }
        Label { text: page.cfg.cleanup ? ("Saved: " + (page.cfg.cleanup.vocabulary || []).join(", ")) : ""; color: colors.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        function addVocabulary() { if (vocabulary.text.trim().length > 0) { page.config("cleanup.vocabulary", vocabulary.text.trim()); vocabulary.text = ""; bridge.sendOp("config_get"); } }
    }
    ColumnLayout {
        Layout.fillWidth: true
        spacing: 12
        visible: page.step === 4
        Label { text: "Choose your defaults now or keep the safe defaults:"; color: colors.text; font.bold: true }
        ComboBox { model: ["economy", "balanced", "ready"]; currentIndex: Math.max(0, ["economy", "balanced", "ready"].indexOf(page.cfg.general ? page.cfg.general.residency_profile : "economy")); onActivated: page.config("general.residency_profile", currentText) }
        Label { text: "Economy unloads the model after each dictation. Balanced and Ready trade memory for faster repeat dictation."; color: colors.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
    }

    RowLayout {
        Layout.fillWidth: true
        VaaniButton { visible: page.step > 0; text: "Back"; tone: "secondary"; onClicked: page.step-- }
        Item { Layout.fillWidth: true }
        VaaniButton {
            text: page.step === 4 ? "Finish setup" : "Continue"
            onClicked: {
                if (page.step < 4) page.step++;
                else { page.config("general.onboarding_complete", "true"); page.finished(); }
            }
        }
    }
}
