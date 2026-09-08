import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Popup {
    id: root
    objectName: "BackgroundRemoverWelcomeOverlay"
    parent: Overlay.overlay
    width: parent ? parent.width : 0
    height: parent ? parent.height : 0
    padding: 0
    margins: 0
    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    signal openRequested()

    function dismiss(openTool) {
        settings.acknowledgeBackgroundRemoverNotice()
        close()
        if (openTool)
            openRequested()
    }

    onOpened: acknowledge.forceActiveFocus()
    background: Item { }
    Overlay.modal: Item { }

    contentItem: Item {
        Accessible.role: Accessible.Dialog
        Accessible.name: "New local background remover"
        Keys.onEscapePressed: root.dismiss(false)

        Rectangle { anchors.fill: parent; color: "#bb000000" }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            onWheel: function(wheel) { wheel.accepted = true }
        }
        Rectangle {
            id: panel
            objectName: "BackgroundRemoverWelcomePanel"
            anchors.centerIn: parent
            width: Math.min(Theme.px(620), Math.max(0, root.width - Theme.px(40)))
            height: Math.min(body.implicitHeight + actions.implicitHeight + Theme.px(68),
                             Math.max(0, root.height - Theme.px(40)))
            color: Qt.rgba(Theme.surfaceRaised.r, Theme.surfaceRaised.g, Theme.surfaceRaised.b, 1)
            radius: Theme.corner(Theme.px(8))
            border.width: Theme.px(1)
            border.color: Theme.borderStrong

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.px(24)
                spacing: Theme.px(20)
                FastScrollView {
                    id: messageScroll
                    objectName: "BackgroundRemoverWelcomeScroll"
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
                                objectName: "BackgroundRemoverWelcomeArt"
                                Layout.preferredWidth: Theme.px(64)
                                Layout.preferredHeight: Theme.px(80)
                                source: root.visible ? assetRoot + "/mini-kloudy.png" : ""
                                fillMode: Image.PreserveAspectFit
                                sourceSize.width: Theme.px(128)
                                sourceSize.height: Theme.px(160)
                            }
                            Text {
                                objectName: "BackgroundRemoverWelcomeTitle"
                                Layout.fillWidth: true
                                text: "Meet your local background remover!"
                                wrapMode: Text.Wrap
                                color: Theme.primaryBright
                                font.family: Theme.displayFamily
                                font.pixelSize: Theme.px(24)
                                font.bold: true
                            }
                        }
                        Text {
                            objectName: "BackgroundRemoverWelcomeMessage"
                            width: parent.width
                            text: "You can now remove backgrounds right inside KFPS. Your images stay on your computer, with modes for anime, illustrations, and flat-colour logos."
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(16)
                        }
                        Text {
                            objectName: "BackgroundRemoverWelcomeCorrections"
                            width: parent.width
                            text: "Tricky background? Touch up the result with erase and restore tools, then save a transparent PNG or use it as your generator source. You'll find it under Tools whenever you need it."
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Theme.text
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(15)
                        }
                        Text {
                            objectName: "BackgroundRemoverWelcomeDownload"
                            width: parent.width
                            text: "AI modes download their files on first use, then work offline. Logo mode needs no extra download."
                            textFormat: Text.PlainText
                            wrapMode: Text.Wrap
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(13)
                        }
                    }
                }
                RowLayout {
                    id: actions
                    Layout.fillWidth: true
                    spacing: Theme.px(10)
                    GhostButton {
                        id: acknowledge
                        objectName: "BackgroundRemoverWelcomeGotIt"
                        text: "Got it"
                        toolTipText: "Dismiss this notice. It will not be shown again."
                        onClicked: root.dismiss(false)
                    }
                    Item { Layout.fillWidth: true }
                    PrimaryButton {
                        objectName: "BackgroundRemoverWelcomeOpen"
                        text: "Open Background Remover"
                        iconName: "cutout"
                        toolTipText: "Open the local background remover. Nothing is downloaded until you start an AI job."
                        onClicked: root.dismiss(true)
                    }
                }
            }
        }
    }
}
