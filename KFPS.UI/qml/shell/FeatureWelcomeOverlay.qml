import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Popup {
    id: root
    objectName: "FeatureWelcomeOverlay"
    parent: Overlay.overlay
    width: parent ? parent.width : 0
    height: parent ? parent.height : 0
    padding: 0
    margins: 0
    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    property Item targetItem
    property rect targetRect: Qt.rect(0, 0, 0, 0)
    signal upscalerRequested()

    function syncTarget() {
        if (!targetItem || !visible)
            return
        var point = targetItem.mapToItem(root.contentItem, 0, 0)
        var bounds = Qt.rect(point.x - Theme.px(4), point.y - Theme.px(4),
                             targetItem.width + Theme.px(8), targetItem.height + Theme.px(8))
        if (bounds.x !== targetRect.x || bounds.y !== targetRect.y || bounds.width !== targetRect.width || bounds.height !== targetRect.height) {
            targetRect = bounds
            arrow.requestPaint()
        }
    }

    function dismiss(openUpscaler) {
        settings.acknowledgeSupportUpscalerNotice()
        close()
        if (openUpscaler)
            upscalerRequested()
    }

    onOpened: {
        syncTarget()
        acknowledge.forceActiveFocus()
    }
    onWidthChanged: if (visible) Qt.callLater(syncTarget)
    onHeightChanged: if (visible) Qt.callLater(syncTarget)
    background: Item { }
    Overlay.modal: Item { }

    contentItem: Item {
        Accessible.role: Accessible.Dialog
        Accessible.name: "KFPS support and upscaler announcement"
        Keys.onEscapePressed: root.dismiss(false)

        // Keep the actual report button visible through the otherwise dimmed shell.
        Rectangle { width: parent.width; height: Math.max(0, root.targetRect.y); color: "#bb000000" }
        Rectangle {
            y: root.targetRect.y + root.targetRect.height
            width: parent.width; height: Math.max(0, parent.height - y); color: "#bb000000"
        }
        Rectangle { y: root.targetRect.y; width: Math.max(0, root.targetRect.x); height: root.targetRect.height; color: "#bb000000" }
        Rectangle {
            x: root.targetRect.x + root.targetRect.width; y: root.targetRect.y
            width: Math.max(0, parent.width - x); height: root.targetRect.height; color: "#bb000000"
        }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            onWheel: function(wheel) { wheel.accepted = true }
        }
        Rectangle {
            objectName: "WelcomeReportSpotlight"
            x: root.targetRect.x; y: root.targetRect.y
            width: root.targetRect.width; height: root.targetRect.height
            color: "transparent"
            radius: Theme.corner(Theme.px(5))
            border.width: Theme.px(2)
            border.color: Theme.primaryBright
        }
        Canvas {
            id: arrow
            objectName: "WelcomeReportArrow"
            property color lineColor: Theme.primaryBright
            onLineColorChanged: requestPaint()
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                var endX = root.targetRect.x + root.targetRect.width + Theme.px(7)
                var endY = root.targetRect.y + root.targetRect.height / 2
                var startX = panel.x + Theme.px(46)
                var startY = panel.y + panel.height + Theme.px(5)
                ctx.strokeStyle = lineColor
                ctx.lineWidth = Theme.px(3)
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.beginPath()
                ctx.moveTo(startX, startY)
                ctx.bezierCurveTo(startX, endY, endX + Theme.px(75), endY, endX, endY)
                ctx.moveTo(endX + Theme.px(13), endY - Theme.px(9))
                ctx.lineTo(endX, endY)
                ctx.lineTo(endX + Theme.px(13), endY + Theme.px(9))
                ctx.stroke()
            }
        }
        Rectangle {
            id: panel
            objectName: "WelcomeAnnouncementPanel"
            width: Math.min(Theme.px(610), root.width - root.targetRect.x - root.targetRect.width - Theme.px(92))
            height: Math.min(body.implicitHeight + actions.implicitHeight + Theme.px(68), root.height - Theme.px(90))
            x: Math.min(root.width - width - Theme.px(24),
                        Math.max(root.targetRect.x + root.targetRect.width + Theme.px(60), (root.width - width) / 2))
            y: Math.max(Theme.px(32), Math.min((root.height - height) / 2, root.targetRect.y - height - Theme.px(54)))
            color: Qt.rgba(Theme.surfaceRaised.r, Theme.surfaceRaised.g, Theme.surfaceRaised.b, 1)
            radius: Theme.corner(Theme.px(8))
            border.width: Theme.px(1)
            border.color: Theme.borderStrong
            onXChanged: arrow.requestPaint()
            onYChanged: arrow.requestPaint()
            onHeightChanged: arrow.requestPaint()

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.px(24)
                spacing: Theme.px(20)
                FastScrollView {
                    id: messageScroll
                    objectName: "WelcomeMessageScroll"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: availableWidth
                    contentHeight: body.implicitHeight
                    rightPadding: Theme.classicMode ? Theme.px(20) : 0
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    clip: true
                    Column {
                        id: body
                        width: messageScroll.availableWidth
                        spacing: Theme.px(14)
                        RowLayout {
                            width: parent.width
                            spacing: Theme.px(16)
                            Image {
                                Layout.preferredWidth: Theme.px(64)
                                Layout.preferredHeight: Theme.px(72)
                                source: root.visible ? assetRoot + "/mini-kloudy.png" : ""
                                fillMode: Image.PreserveAspectFit
                                sourceSize.width: Theme.px(128)
                                sourceSize.height: Theme.px(144)
                            }
                            Text {
                                text: "Hello!"
                                color: Theme.primaryBright
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(28)
                                font.bold: true
                                Layout.fillWidth: true
                            }
                        }
                        Text {
                            objectName: "WelcomeSupportMessage"
                            width: parent.width
                            text: "Because of some changes, the old support channel is not an option anymore and I'll be taking reports through KFPS from now on. Reports will land in the KFPS Support server. Thank you!"
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(16)
                        }
                        Rectangle { width: parent.width; height: Theme.px(1); color: Theme.border }
                        Text {
                            width: parent.width
                            text: "Also new: a built-in image upscaler"
                            wrapMode: Text.Wrap
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(16)
                            font.bold: true
                        }
                        Text {
                            objectName: "WelcomeUpscalerMessage"
                            width: parent.width
                            text: "Give photos, anime, text and logos a 2x or 4x boost. Find it under Tools > Open Upscaler. Your images stay on your computer."
                            wrapMode: Text.Wrap
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(14)
                        }
                    }
                }
                RowLayout {
                    id: actions
                    Layout.fillWidth: true
                    spacing: Theme.px(10)
                    GhostButton {
                        objectName: "WelcomeTryUpscaler"
                        text: "Try the upscaler"
                        iconName: "upscale"
                        toolTipText: "Dismiss this notice and open the local image upscaler."
                        onClicked: root.dismiss(true)
                    }
                    Item { Layout.fillWidth: true }
                    PrimaryButton {
                        id: acknowledge
                        objectName: "WelcomeGotIt"
                        text: "Got it"
                        toolTipText: "Dismiss this announcement. It will not be shown again."
                        onClicked: root.dismiss(false)
                    }
                }
            }
        }
        Timer {
            interval: 100
            running: root.visible
            repeat: true
            onTriggered: root.syncTarget()
        }
    }
}
