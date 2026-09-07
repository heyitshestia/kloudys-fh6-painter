import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Popup {
    id: root
    objectName: "CommunityWelcomeOverlay"
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
    property date currentDate: new Date()
    readonly property bool contestActive: currentDate.getTime() < new Date(2026, 9, 1).getTime()
    signal joinRequested()

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

    function dismiss(join) {
        settings.acknowledgeCommunityJoinNotice()
        close()
        if (join)
            joinRequested()
    }

    onOpened: {
        currentDate = new Date()
        syncTarget()
        acknowledge.forceActiveFocus()
    }
    onWidthChanged: if (visible) Qt.callLater(syncTarget)
    onHeightChanged: if (visible) Qt.callLater(syncTarget)
    background: Item { }
    Overlay.modal: Item { }

    contentItem: Item {
        Accessible.role: Accessible.Dialog
        Accessible.name: "Join the KFPS community"
        Keys.onEscapePressed: root.dismiss(false)

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
            objectName: "CommunityJoinSpotlight"
            x: root.targetRect.x; y: root.targetRect.y
            width: root.targetRect.width; height: root.targetRect.height
            color: "transparent"
            radius: Theme.corner(Theme.px(5))
            border.width: Theme.px(2)
            border.color: Theme.primaryBright
        }
        Canvas {
            id: arrow
            property color lineColor: Theme.primaryBright
            onLineColorChanged: requestPaint()
            anchors.fill: parent
            onPaint: {
                var ctx = getContext("2d")
                ctx.reset()
                var endX = root.targetRect.x + root.targetRect.width / 2
                var endY = root.targetRect.y + root.targetRect.height + Theme.px(5)
                var startX = panel.x + Theme.px(40)
                var startY = panel.y - Theme.px(4)
                ctx.strokeStyle = lineColor
                ctx.lineWidth = Theme.px(3)
                ctx.lineCap = "round"
                ctx.lineJoin = "round"
                ctx.beginPath()
                ctx.moveTo(startX, startY)
                ctx.bezierCurveTo(startX, endY + Theme.px(35), endX, startY, endX, endY)
                ctx.moveTo(endX - Theme.px(8), endY + Theme.px(12))
                ctx.lineTo(endX, endY)
                ctx.lineTo(endX + Theme.px(8), endY + Theme.px(12))
                ctx.stroke()
            }
        }
        Rectangle {
            id: panel
            objectName: "CommunityWelcomePanel"
            width: Math.min(Theme.px(640), root.width - Theme.px(48))
            height: Math.min(body.implicitHeight + actions.implicitHeight + Theme.px(68),
                             root.height - root.targetRect.y - root.targetRect.height - Theme.px(60))
            x: (root.width - width) / 2
            y: Math.max(root.targetRect.y + root.targetRect.height + Theme.px(36), (root.height - height) / 2)
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
                    objectName: "CommunityWelcomeScroll"
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
                        spacing: Theme.px(16)
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
                                Layout.fillWidth: true
                                text: "Come say hello!"
                                wrapMode: Text.Wrap
                                color: Theme.primaryBright
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(26)
                                font.bold: true
                            }
                        }
                        Text {
                            objectName: "CommunityWelcomeMessage"
                            width: parent.width
                            text: "Need help, found a bug, or made something you're proud of? Come join the KFPS Support server! It's a place to report issues, share your work and screenshots, and chat with other creators. We'd love to see you there."
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(16)
                        }
                        Column {
                            objectName: "CommunityContestSection"
                            width: parent.width
                            spacing: Theme.px(12)
                            visible: root.contestActive
                            Rectangle { width: parent.width; height: Theme.px(1); color: Theme.border }
                            Text {
                                width: parent.width
                                text: "The KFPS Vinyl Contest is still on!"
                                wrapMode: Text.Wrap
                                color: Theme.primaryBright
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(18)
                                font.bold: true
                            }
                            Text {
                                objectName: "CommunityContestEntry"
                                width: parent.width
                                text: "There's still time to enter. Share your submission in the Community tab and include the tag createinsane."
                                textFormat: Text.PlainText
                                wrapMode: Text.Wrap
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(15)
                            }
                            Text {
                                objectName: "CommunityContestDeadline"
                                width: parent.width
                                text: "Deadline: 30 September 2026"
                                wrapMode: Text.Wrap
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(15)
                                font.bold: true
                            }
                            Text {
                                objectName: "CommunityContestPrizes"
                                width: parent.width
                                text: "1st place: a $50 Steam gift card\n2nd and 3rd place: one KFPS supporter key each"
                                wrapMode: Text.Wrap
                                color: Theme.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.px(15)
                            }
                        }
                    }
                }
                RowLayout {
                    id: actions
                    Layout.fillWidth: true
                    spacing: Theme.px(10)
                    GhostButton {
                        id: acknowledge
                        objectName: "CommunityWelcomeGotIt"
                        text: "Got it"
                        toolTipText: "Dismiss this notice. It will not be shown again."
                        onClicked: root.dismiss(false)
                    }
                    Item { Layout.fillWidth: true }
                    PrimaryButton {
                        objectName: "CommunityWelcomeJoin"
                        text: "Join the server"
                        iconName: "community"
                        toolTipText: "Open the KFPS Support server invitation in your default browser."
                        onClicked: root.dismiss(true)
                    }
                }
            }
        }
        Timer { interval: 100; running: root.visible; repeat: true; onTriggered: root.syncTarget() }
        Timer { interval: 60000; running: root.visible; repeat: true; onTriggered: root.currentDate = new Date() }
    }
}
