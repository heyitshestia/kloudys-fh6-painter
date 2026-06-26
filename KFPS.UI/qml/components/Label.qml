import QtQuick 6.7
import Kfps.Theme 1.0

Text {
    color: Theme.subtle
    font.family: Theme.fontFamily
    font.pixelSize: Theme.px(10)
    font.weight: Font.DemiBold
    font.capitalization: Font.AllUppercase
    font.letterSpacing: Theme.px(0.5)
    verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight
}
