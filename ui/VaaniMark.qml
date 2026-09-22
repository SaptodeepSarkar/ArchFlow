// Native recreation of the Vaani lockup used by the Android introduction.
// The short coral stroke is intentional: it distinguishes the mark without
// turning it into a waveform or borrowing another product's symbol.
import QtQuick

Item {
    id: mark
    property bool dark: false
    property bool showWordmark: true
    property real markSize: 30
    property color primaryColor: dark ? "#FFFDFB" : "#6B3A85"
    property color accentColor: "#FFD4A3"
    property color wordmarkColor: dark ? "#FFFDFB" : "#19161C"
    implicitWidth: markSize + (showWordmark ? 74 : 0)
    implicitHeight: markSize

    Canvas {
        id: glyph
        width: mark.markSize
        height: mark.markSize
        antialiasing: true
        property color primary: mark.primaryColor
        property color accent: mark.accentColor

        onPaint: {
            var context = getContext("2d");
            context.clearRect(0, 0, width, height);
            context.lineWidth = Math.max(3, width * 0.12);
            context.lineCap = "round";
            context.lineJoin = "round";

            context.strokeStyle = primary;
            context.beginPath();
            context.moveTo(width * 0.18, height * 0.25);
            context.lineTo(width * 0.50, height * 0.78);
            context.lineTo(width * 0.65, height * 0.52);
            context.stroke();

            context.strokeStyle = accent;
            context.beginPath();
            context.moveTo(width * 0.65, height * 0.52);
            context.lineTo(width * 0.82, height * 0.25);
            context.stroke();
        }
        onPrimaryChanged: requestPaint()
        onAccentChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Component.onCompleted: requestPaint()
    }

    Text {
        visible: mark.showWordmark
        anchors.left: glyph.right
        anchors.leftMargin: 10
        anchors.verticalCenter: glyph.verticalCenter
        text: "Vaani"
        color: mark.wordmarkColor
        font.pixelSize: Math.round(mark.markSize * 0.82)
        font.weight: Font.Bold
        font.letterSpacing: -0.6
    }
}
