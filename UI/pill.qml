import QtQuick
import QtQuick.Controls

// Vaani pill: bottom-center, 3 states + error. States are driven by the
// key service; the pill never loads models itself.
Rectangle {
    id: pill
    width: 420
    height: 64
    radius: 32
    color: "#1e1e2e"

    property string state: "listening" // listening | transcribing | writing | error
    property string words: "speak now ..."
    signal cancelRequested()

    anchors {
        bottom: parent.bottom
        bottomMargin: 48
        horizontalCenter: parent.horizontalCenter
    }

    Column {
        anchors.centerIn: parent
        spacing: 2

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: {
                if (pill.state === "listening") return "● Listening";
                if (pill.state === "transcribing") return "… Transcribing";
                if (pill.state === "writing") return "✎ Writing";
                return "✕ Error";
            }
            color: "#cdd6f4"
            font.pixelSize: 12
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: pill.words
            color: "#ffffff"
            font.pixelSize: 16
            elide: Text.ElideRight
            maximumLineCount: 1
        }
    }

    Button {
        anchors {
            right: parent.right
            rightMargin: 12
            verticalCenter: parent.verticalCenter
        }
        text: "✕"
        flat: true
        onClicked: pill.cancelRequested()
    }
}
