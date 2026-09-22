import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: control
    property string title: ""
    property string description: ""
    property bool checked: false
    property bool busy: false
    signal requested(bool checked)

    implicitHeight: Math.max(58, copy.implicitHeight)
    Layout.fillWidth: true

    RowLayout {
        anchors.fill: parent
        spacing: 18
        ColumnLayout {
            id: copy
            Layout.fillWidth: true
            spacing: 4
            Label { text: control.title; color: "#19161C"; font.pixelSize: 14; font.bold: true; Layout.fillWidth: true }
            Label { text: control.description; color: "#827B87"; font.pixelSize: 12; wrapMode: Text.WordWrap; Layout.fillWidth: true }
        }
        Button {
            id: switchButton
            enabled: !control.busy
            implicitWidth: 52
            implicitHeight: 32
            onClicked: control.requested(!control.checked)
            contentItem: Item { }
            background: Rectangle {
                radius: height / 2
                color: control.checked ? "#6B3A85" : "#E8E2E7"
                opacity: switchButton.enabled ? 1 : 0.5
                Rectangle {
                    width: 24; height: 24; radius: 12
                    anchors.verticalCenter: parent.verticalCenter
                    x: control.checked ? parent.width - width - 4 : 4
                    color: "#FFFDFB"
                    Behavior on x { NumberAnimation { duration: 180 } }
                }
            }
        }
    }
}
