import QtQuick 6.7
import Kfps.Theme 1.0

Item {
    id: root

    Image {
        anchors.fill: parent
        source: assetRoot + "/night-blossom-base.png"
        fillMode: Image.PreserveAspectCrop
        smooth: true
        mipmap: true
    }

    Image {
        id: topBranch
        source: assetRoot + "/branch-top.png"
        width: parent.width * 0.70
        height: parent.height * 0.46
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: -parent.width * 0.015
        anchors.topMargin: -Theme.px(5)
        fillMode: Image.PreserveAspectFit
        transformOrigin: Item.TopRight
        opacity: 0.78
        smooth: true
        mipmap: true
        SequentialAnimation on rotation {
            running: Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
            loops: Animation.Infinite
            NumberAnimation { from: -0.18; to: 0.22; duration: 9000; easing.type: Easing.InOutSine }
            NumberAnimation { from: 0.22; to: -0.18; duration: 9000; easing.type: Easing.InOutSine }
        }
    }

    Image {
        id: bottomBranch
        source: assetRoot + "/branch-bottom.png"
        width: parent.width * 0.36
        height: parent.height * 0.42
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.leftMargin: -parent.width * 0.03
        anchors.bottomMargin: -parent.height * 0.02
        fillMode: Image.PreserveAspectFit
        transformOrigin: Item.BottomLeft
        opacity: 0.62
        smooth: true
        mipmap: true
        SequentialAnimation on rotation {
            running: Theme.ambientMotion && !Theme.reducedMotion && !screenshotMode
            loops: Animation.Infinite
            NumberAnimation { from: 0.18; to: -0.20; duration: 10400; easing.type: Easing.InOutSine }
            NumberAnimation { from: -0.20; to: 0.18; duration: 10400; easing.type: Easing.InOutSine }
        }
    }

    PetalField { anchors.fill: parent }

    Rectangle {
        anchors.fill: parent
        color: "transparent"
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#0d000000" }
            GradientStop { position: 0.58; color: "#05000000" }
            GradientStop { position: 1.0; color: "#35000000" }
        }
    }
}
