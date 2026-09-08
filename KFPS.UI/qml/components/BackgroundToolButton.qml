import QtQuick 6.7
import QtQuick.Controls 6.7
import Kfps.Theme 1.0

ToolButton {
    id: control
    property string glyph: "hand"
    property string help: ""
    implicitWidth: Theme.px(36)
    implicitHeight: Theme.px(36)
    display: AbstractButton.IconOnly
    icon.source: assetRoot + "/background-remover-icons/" + glyph + ".svg"
    icon.width: Theme.px(20)
    icon.height: Theme.px(20)
    icon.color: enabled ? Theme.text : Theme.muted
    text: help
    Accessible.name: help
    ToolTip.visible: hovered
    ToolTip.delay: 350
    ToolTip.text: help
    background: Rectangle {
        radius: Theme.corner(Theme.px(3))
        color: control.checked ? Theme.surface : "transparent"
        border.width: control.checked || control.hovered ? 1 : 0
        border.color: control.checked ? Theme.primaryBright : Theme.border
        opacity: control.enabled ? 1 : 0.45
    }
}
