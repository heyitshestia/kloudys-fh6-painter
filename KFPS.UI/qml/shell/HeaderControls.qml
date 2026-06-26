import QtQuick 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

GlassPanel {
    id: root

    property bool compact: false

    width: Theme.px(compact ? 240 : 300)
    height: Theme.px(46)
    radius: Theme.px(13)
    soft: true

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.px(13)
        anchors.rightMargin: Theme.px(8)
        spacing: Theme.px(10)

        Text {
            visible: !root.compact
            text: "Theme"
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(10.5)
            verticalAlignment: Text.AlignVCenter
            Layout.alignment: Qt.AlignVCenter
        }

        KfpsComboBox {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            dense: true
            model: ["Night Blossom"]
            currentIndex: 0
            enabled: true
        }
    }
}
