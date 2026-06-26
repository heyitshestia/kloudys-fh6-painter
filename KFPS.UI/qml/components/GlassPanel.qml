import QtQuick 6.7
import QtQuick.Effects 6.7
import Kfps.Theme 1.0

Rectangle {
    id: root
    property bool strong: false
    property bool soft: false
    property bool raised: false
    property bool glow: false
    property real panelOpacity: 1.0
    property real shadowStrength: raised ? 0.72 : 0.52

    radius: Theme.px(13)
    color: "transparent"
    opacity: panelOpacity
    border.width: Math.max(1, Theme.px(1))
    border.color: raised ? Theme.borderStrong : (soft ? Theme.borderSoft : Theme.border)
    antialiasing: true

    gradient: Gradient {
        GradientStop {
            position: 0.0
            color: root.soft ? "#ae160d1b" : (root.strong ? Theme.surfaceStrongTop : Theme.surfaceTop)
        }
        GradientStop {
            position: 0.42
            color: root.soft ? "#a70e0914" : (root.strong ? "#d9251730" : "#bf1d1225")
        }
        GradientStop {
            position: 1.0
            color: root.soft ? "#b908060d" : (root.strong ? Theme.surfaceStrongBottom : Theme.surfaceBottom)
        }
    }

    layer.enabled: Theme.glassEffects && !screenshotMode
    layer.smooth: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: root.glow ? "#b73e0d3d" : Theme.shadow
        shadowBlur: root.raised ? 0.86 : 0.62
        shadowHorizontalOffset: 0
        shadowVerticalOffset: root.raised ? Theme.px(7) : Theme.px(4)
        shadowOpacity: root.glow ? 0.74 : root.shadowStrength
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: Theme.px(1)
        radius: Math.max(0, root.radius - Theme.px(1))
        color: "transparent"
        border.width: Math.max(1, Theme.px(1))
        border.color: root.strong ? "#3c9c5a83" : Theme.innerHighlight
        opacity: 0.72
        antialiasing: true
    }


    Image {
        anchors.fill: parent
        source: assetRoot + "/glass-noise.png"
        fillMode: Image.Tile
        opacity: root.soft ? 0.022 : 0.038
        smooth: true
        clip: true
    }
}
