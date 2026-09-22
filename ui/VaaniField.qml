import QtQuick
import QtQuick.Controls

TextField {
    id: field
    implicitHeight: 50
    leftPadding: 16
    rightPadding: 16
    color: "#19161C"
    placeholderTextColor: "#827B87"
    font.pixelSize: 14
    background: Rectangle {
        radius: 16
        color: "#FFFDFB"
        border.width: field.activeFocus ? 2 : 1
        border.color: field.activeFocus ? "#6B3A85" : "#E8E2E7"
    }
}
