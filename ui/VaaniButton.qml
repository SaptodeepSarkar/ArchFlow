import QtQuick
import QtQuick.Controls

Button {
    id: control
    property string tone: "primary"
    property bool darkSurface: false
    implicitHeight: 50
    leftPadding: 20
    rightPadding: 20
    font.pixelSize: 14
    font.weight: Font.DemiBold
    contentItem: Text {
        text: control.text
        color: control.tone === "dark" || (control.darkSurface && control.tone !== "primary") ? "#FDFBF8" : "#19161C"
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    background: Rectangle {
        radius: 16
        color: control.tone === "primary" ? "#E8DCFF" : control.tone === "dark" ? "#19161C" : "transparent"
        border.width: control.tone === "text" ? 0 : 2
        border.color: control.tone === "primary" ? "#57505C" : control.tone === "dark" ? "#19161C" : control.darkSurface ? "#99FFFDFB" : "#57505C"
        opacity: control.enabled ? 1 : 0.45
    }
}
