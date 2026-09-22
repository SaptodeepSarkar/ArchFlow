// A window-overlay popup keeps choices above Flickables and within the app's
// visual order instead of relying on the platform's unstyled ComboBox menu.
import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    implicitHeight: 50
    property var values: []
    property string selectedValue: currentIndex >= 0 ? String(currentText) : ""
    signal valueSelected(string value)

    model: values
    font.pixelSize: 14
    leftPadding: 16
    rightPadding: 42

    onActivated: valueSelected(String(currentText))

    contentItem: Text {
        leftPadding: control.leftPadding
        rightPadding: control.rightPadding
        text: control.displayText
        color: "#19161C"
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        anchors.right: parent.right
        anchors.rightMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        text: control.popup.visible ? "⌃" : "⌄"
        color: "#6B3A85"
        font.pixelSize: 18
    }
    background: Rectangle {
        radius: 16
        color: "#FFFDFB"
        border.width: control.activeFocus || control.popup.visible ? 2 : 1
        border.color: control.activeFocus || control.popup.visible ? "#6B3A85" : "#E8E2E7"
    }
    delegate: ItemDelegate {
        id: option
        required property var modelData
        width: control.width - 8
        height: 42
        leftPadding: 14
        rightPadding: 14
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: String(option.modelData)
            color: "#19161C"
            font.pixelSize: 14
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: 11
            color: option.highlighted || control.currentIndex === index ? "#E8DCFF" : "transparent"
        }
    }
    popup: Popup {
        id: choices
        parent: Overlay.overlay
        width: control.width
        x: Overlay.overlay ? control.mapToItem(Overlay.overlay, 0, 0).x : 0
        y: {
            if (!Overlay.overlay)
                return control.height + 8;
            var below = control.mapToItem(Overlay.overlay, 0, control.height + 8).y;
            var maximum = Overlay.overlay.height - implicitHeight - 12;
            return Math.max(12, Math.min(below, maximum));
        }
        implicitHeight: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, 226)
        topPadding: 4
        bottomPadding: 4
        leftPadding: 4
        rightPadding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        background: Rectangle {
            radius: 16
            color: "#FFFDFB"
            border.width: 1
            border.color: "#D4BBFF"
        }
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.delegateModel
            currentIndex: control.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }
    }
}
