// Historical Quickshell lockup; the native GTK app uses the same source mark.
import QtQuick

Item {
    id: mark
    property bool dark: false
    property bool showWordmark: true
    property real markSize: 30
    property color wordmarkColor: dark ? "#FFFDFB" : "#243D4A"
    implicitWidth: markSize + (showWordmark ? 74 : 0)
    implicitHeight: markSize

    Image {
        id: glyph
        source: "../brand/vaani-mark.svg"
        width: mark.markSize
        height: mark.markSize
        sourceSize.width: width * 2
        sourceSize.height: height * 2
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
