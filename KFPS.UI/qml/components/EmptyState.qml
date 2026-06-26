import QtQuick 6.7
import Kfps.Theme 1.0

Column {
    id: root

    property string iconName: "images"
    property string title: "Nothing selected"
    property string message: ""
    spacing: Theme.px(9)

    Icon {
        name: root.iconName
        iconSize: Theme.px(45)
        iconOpacity: 0.42
        glow: true
        anchors.horizontalCenter: parent.horizontalCenter
    }

    Text {
        width: root.parent ? root.parent.width * 0.8 : Theme.px(320)
        text: root.title
        color: Theme.text
        font.family: Theme.displayFamily
        font.pixelSize: Theme.px(18)
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.Wrap
        maximumLineCount: 2
        elide: Text.ElideRight
        anchors.horizontalCenter: parent.horizontalCenter
    }

    Text {
        width: Math.min(Theme.px(360), root.parent ? root.parent.width * 0.8 : Theme.px(360))
        text: root.message
        color: Theme.muted
        font.family: Theme.fontFamily
        font.pixelSize: Theme.px(11.5)
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
        anchors.horizontalCenter: parent.horizontalCenter
    }
}
