// Desktop first-run story, deliberately kept to the same short product arc as
// Android: promise, language, writing everywhere, then a clear ready state.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell

Rectangle {
    id: page
    anchors.fill: parent
    property int step: 0
    property var cfg: ({})
    readonly property bool isIntro: step < 3
    readonly property bool animationEnabled: Quickshell.env("VAANI_REDUCE_MOTION") !== "1"
    property real contentOpacity: animationEnabled ? 0 : 1
    property real contentOffset: animationEnabled ? 22 : 0
    property real artworkScale: animationEnabled ? 1.045 : 1
    readonly property var titleTop: ["The thought.", "Your voice,", "Wherever you", "Ready for your"]
    readonly property var titleBottom: ["Written.", "your language.", "write.", "first thought."]
    readonly property var bodyTop: [
        "Vaani turns speech into clean writing while keeping your audio",
        "Speak naturally. Choose your model and language later when you",
        "Use your shortcut in the text fields where your work already",
        "Press SUPER+H to dictate. Change the shortcut, service, model,"
    ]
    readonly property var bodyBottom: [
        "and raw dictation on this device.",
        "want more control.",
        "happens.",
        "and vocabulary in Settings."
    ]
    readonly property var art: ["assets/onboarding_v2_arrival.png", "assets/onboarding_v2_language.png", "assets/onboarding_v2_everywhere.png"]

    required property var bridge
    required property var colors
    signal finished()

    color: isIntro ? "#19161C" : "#FDFBF8"

    Component.onCompleted: { bridge.settingsApi = page; bridge.sendOp("config_get"); playEntrance(); }
    Component.onDestruction: if (bridge.settingsApi === page) bridge.settingsApi = null
    onStepChanged: playEntrance()

    function routeData(data) {
        if (data.general && data.recognition)
            cfg = data;
    }
    function finishSetup() {
        bridge.sendOp("config_set", {key: "general.onboarding_complete", value: "true"});
        finished();
    }
    function playEntrance() {
        if (!animationEnabled) {
            contentOpacity = 1;
            contentOffset = 0;
            artworkScale = 1;
            return;
        }
        contentOpacity = 0;
        contentOffset = 22;
        artworkScale = 1.045;
        entrance.restart();
    }

    ParallelAnimation {
        id: entrance
        NumberAnimation { target: page; property: "contentOpacity"; to: 1; duration: 340; easing.type: Easing.OutCubic }
        NumberAnimation { target: page; property: "contentOffset"; to: 0; duration: 460; easing.type: Easing.OutCubic }
        NumberAnimation { target: page; property: "artworkScale"; to: 1; duration: 780; easing.type: Easing.OutCubic }
    }

    Image {
        id: artwork
        anchors.fill: parent
        visible: page.isIntro
        source: page.isIntro && page.step < page.art.length ? page.art[page.step] : ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        opacity: status === Image.Ready ? 0.72 : 0
        scale: page.artworkScale
        transformOrigin: Item.Center
    }
    Rectangle {
        anchors.fill: parent
        visible: page.isIntro
        gradient: Gradient {
            GradientStop { position: 0; color: "#EB19161C" }
            GradientStop { position: 0.43; color: "#6119161C" }
            GradientStop { position: 1; color: "#F219161C" }
        }
    }
    // Plain-colour fallback remains useful when artwork has not loaded yet.
    Rectangle {
        visible: !page.isIntro && page.step === 3
        anchors.fill: parent
        color: "#FDFBF8"
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 34
        anchors.rightMargin: 34
        anchors.topMargin: 34
        // The action rail is outside this layout and always owns the bottom
        // of the window, even when a font or translated copy grows taller.
        anchors.bottomMargin: 122
        spacing: 0
        opacity: page.contentOpacity
        transform: Translate { y: page.contentOffset }

        VaaniMark {
            markSize: 30
            dark: page.isIntro
            wordmarkColor: page.isIntro ? "#FFFDFB" : "#19161C"
        }

        Item { Layout.preferredHeight: page.isIntro ? 42 : 24 }

        Column {
            Layout.fillWidth: true
            Layout.preferredHeight: 100
            Text {
                width: parent.width
                text: page.titleTop[page.step]
                color: page.isIntro ? "#FFFDFB" : "#19161C"
                font.family: "Georgia"
                font.pixelSize: 42
                font.weight: Font.Normal
            }
            Text {
                width: parent.width
                text: page.titleBottom[page.step]
                color: page.isIntro ? "#FFFDFB" : "#19161C"
                font.family: "Georgia"
                font.pixelSize: 42
                font.weight: Font.Normal
            }
        }
        Item { Layout.preferredHeight: 16 }
        Column {
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            spacing: 2
            Text {
                width: parent.width
                text: page.bodyTop[page.step]
                color: page.isIntro ? "#FFFDFB" : "#57505C"
                opacity: page.isIntro ? 0.9 : 1
                font.pixelSize: 16
            }
            Text {
                width: parent.width
                text: page.bodyBottom[page.step]
                color: page.isIntro ? "#FFFDFB" : "#57505C"
                opacity: page.isIntro ? 0.9 : 1
                font.pixelSize: 16
            }
        }

        Item {
            id: languageRail
            visible: page.step === 1
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 132 : 0
            clip: true
            property real travel: 0
            property var words: ["অসমীয়া", "বাংলা", "ગુજરાતી", "हिन्दी", "ಕನ್ನಡ", "മലയാളം", "मराठी", "தமிழ்", "తెలుగు"]
            NumberAnimation on travel {
                from: 0; to: languageRail.words.length * 48
                duration: 6200
                loops: Animation.Infinite
                running: languageRail.visible && page.animationEnabled
            }
            Repeater {
                model: languageRail.words.length * 3
                Rectangle {
                    required property int index
                    readonly property real railY: index * 48 - languageRail.travel
                    width: Math.min(270, languageRail.width - 32)
                    height: 38
                    x: (languageRail.width - width) / 2
                    y: railY
                    radius: 19
                    color: "#1AFFFDFB"
                    border.width: 1
                    border.color: "#4DFFFDFB"
                    opacity: Math.max(0.18, 1 - Math.abs(railY - 50) / 104)
                    scale: 0.92 + opacity * 0.08
                    Label { anchors.centerIn: parent; text: languageRail.words[index % languageRail.words.length]; color: "#FFFDFB"; font.pixelSize: 16; font.bold: true }
                }
            }
        }

        Item {
            id: placeRail
            visible: page.step === 2
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 132 : 0
            clip: true
            property real travel: 0
            property var destinations: [
                { name: "Slack", icon: "assets/brand_slack.png" },
                { name: "WhatsApp", icon: "assets/brand_whatsapp.png" },
                { name: "Gmail", icon: "assets/brand_gmail.png" },
                { name: "Notion", icon: "assets/brand_notion.png" },
                { name: "Telegram", icon: "assets/brand_telegram.png" },
                { name: "Canva", icon: "assets/brand_canva.png" }
            ]
            NumberAnimation on travel {
                from: 0; to: 1
                duration: 8200
                loops: Animation.Infinite
                running: placeRail.visible && page.animationEnabled
            }
            Repeater {
                model: placeRail.destinations
                Rectangle {
                    required property int index
                    required property var modelData
                    readonly property real progress: (index / placeRail.destinations.length - placeRail.travel + 1) % 1
                    width: 112; height: 48; radius: 16
                    x: progress * (placeRail.width + width) - width
                    y: 42 + Math.sin(progress * Math.PI * 2) * 25
                    rotation: -12 + progress * 24
                    color: "#E8DCFF"
                    border.width: 1; border.color: "#D4BBFF"
                    Row {
                        anchors.centerIn: parent; spacing: 8
                        Image { width: 22; height: 22; source: modelData.icon; fillMode: Image.PreserveAspectFit; asynchronous: true }
                        Label { text: modelData.name; color: "#19161C"; font.pixelSize: 12; font.bold: true }
                    }
                }
            }
        }

        ColumnLayout {
            visible: page.step === 3
            Layout.fillWidth: true
            Layout.topMargin: visible ? 18 : 0
            spacing: 14
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 112
                radius: 22
                color: "#E8DCFF"
                Column {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 7
                    Label { text: "PRIMARY SHORTCUT"; color: "#54296C"; font.pixelSize: 10; font.bold: true; font.letterSpacing: 1.3 }
                    Label { text: page.cfg.general ? page.cfg.general.shortcut : "SUPER+H"; color: "#19161C"; font.pixelSize: 26; font.bold: true }
                    Label { text: "Manage the service in Settings whenever you need it."; color: "#57505C"; font.pixelSize: 12 }
                }
            }
            Label { text: "Vaani’s menu includes a start-at-login switch and a full service start/stop control."; color: "#827B87"; font.pixelSize: 13; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }

        Item { Layout.fillHeight: true }
    }

    Row {
        id: onboardingDots
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: onboardingActions.top
        anchors.bottomMargin: 16
        opacity: page.contentOpacity
        transform: Translate { y: page.contentOffset }
        spacing: 8
        Repeater {
            model: 4
            Rectangle {
                required property int index
                width: page.step === index ? 22 : 7
                height: 7
                radius: 4
                color: page.step === index ? (page.isIntro ? "#FFD4A3" : "#6B3A85") : (page.isIntro ? "#FFFDFB66" : "#D4BBFF")
                Behavior on width { NumberAnimation { duration: 180 } }
            }
        }
    }
    RowLayout {
        id: onboardingActions
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 34
        anchors.rightMargin: 34
        anchors.bottomMargin: 34
        height: 50
        opacity: page.contentOpacity
        transform: Translate { y: page.contentOffset }
        VaaniButton {
            visible: page.step > 0
            text: "Back"
            tone: "secondary"
            darkSurface: page.isIntro
            onClicked: page.step--
        }
        Item { Layout.fillWidth: true }
        VaaniButton {
            text: page.step === 0 ? "Get started" : page.step === 3 ? "Open Vaani" : "Next"
            onClicked: {
                if (page.step < 3)
                    page.step++;
                else
                    page.finishSetup();
            }
        }
    }
}
