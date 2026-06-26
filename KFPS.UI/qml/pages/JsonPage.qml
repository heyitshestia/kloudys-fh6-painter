import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root

    anchors.fill: parent
    property bool wide: Theme.logical(width) >= 1120

    TapHandler {
        acceptedButtons: Qt.LeftButton
        gesturePolicy: TapHandler.ReleaseWithinBounds
        grabPermissions: PointerHandler.ApprovesTakeOverByAnything
        onTapped: jsonService.clearSelection()
    }

    Loader {
        anchors.fill: parent
        sourceComponent: root.wide ? wideComponent : compactComponent
    }

    Component {
        id: wideComponent

        GridLayout {
            columns: 4
            columnSpacing: Theme.px(10)

            HoverCard {
                Layout.preferredWidth: Theme.px(250)
                Layout.minimumWidth: Theme.px(225)
                Layout.fillHeight: true
                padding: Theme.px(16)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(9)

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "JSON and game tools"
                        subtitle: "Select the exact JSON, then import or export against the active game editor."
                    }

                    ScrollView {
                        id: controlsScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        contentWidth: availableWidth
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        ColumnLayout {
                            width: controlsScroll.availableWidth
                            spacing: Theme.px(8)

                            Label {
                                text: "Game"
                            }
                            KfpsComboBox {
                                id: game
                                Layout.fillWidth: true
                                model: ["FH6", "FH5", "FM8"]
                            }

                            Label {
                                text: "Loaded template / group layers"
                            }
                            KfpsTextField {
                                id: layerCount
                                Layout.fillWidth: true
                                text: "3000"
                                inputMethodHints: Qt.ImhDigitsOnly
                            }

                            Label {
                                text: "JSON source"
                            }
                            KfpsComboBox {
                                id: source
                                Layout.fillWidth: true
                                model: ["Generated finals", "Editor exports", "Exported game JSONs"]
                                onActivated: jsonService.setSource(currentIndex)
                            }

                            PrimaryButton {
                                Layout.fillWidth: true
                                text: "Refresh browser"
                                iconName: "refresh"
                                onClicked: jsonService.refresh()
                            }

                            GhostButton {
                                Layout.fillWidth: true
                                text: "Open source folder"
                                iconName: "folder"
                                onClicked: {
                                    if (jsonService.selectedFolder !== "—")
                                        desktop.openFolder(jsonService.selectedFolder);
                                    else
                                        desktop.openJsonFolders();
                                }
                            }

                            GhostButton {
                                Layout.fillWidth: true
                                text: "Browse JSON manually"
                                onClicked: jsonService.browseManual()
                            }

                            Text {
                                Layout.fillWidth: true
                                text: jsonService.selectedPath || "No JSON selected"
                                color: Theme.subtle
                                font.family: Theme.monoFamily
                                font.pixelSize: Theme.px(9.5)
                                wrapMode: Text.Wrap
                                maximumLineCount: 3
                                elide: Text.ElideMiddle
                            }

                            KfpsCheckBox {
                                id: clearUnused
                                text: "Clear unused template layers"
                                checked: true
                            }
                        }
                    }

                    PrimaryButton {
                        Layout.fillWidth: true
                        text: transferService.running ? "Working…" : "Import JSON"
                        enabled: !transferService.running && jsonService.selectedPath.length > 0
                        onClicked: transferService.importJson(game.currentText, jsonService.selectedPath, parseInt(layerCount.text) || 0, clearUnused.checked)
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        text: "Export current group"
                        enabled: !transferService.running
                        onClicked: transferService.exportJson(game.currentText, parseInt(layerCount.text) || 0)
                    }
                }
            }

            HoverCard {
                Layout.preferredWidth: Theme.px(235)
                Layout.minimumWidth: Theme.px(205)
                Layout.fillHeight: true
                padding: Theme.px(14)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(8)

                    Text {
                        text: "Generations / Folders"
                        color: Theme.primaryBright
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(13)
                        font.weight: Font.DemiBold
                    }

                    ListView {
                        id: groups
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: jsonService.groupModel
                        spacing: Theme.px(4)

                        delegate: GhostButton {
                            required property string name
                            required property int count
                            required property int index
                            width: groups.width
                            minimumWidth: 0
                            text: name + "  (" + count + ")"
                            onClicked: jsonService.selectGroup(index)
                        }
                    }
                }
            }

            HoverCard {
                Layout.preferredWidth: Theme.px(260)
                Layout.minimumWidth: Theme.px(225)
                Layout.fillHeight: true
                padding: Theme.px(14)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(8)

                    Text {
                        text: "Checkpoint JSONs"
                        color: Theme.primaryBright
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(13)
                        font.weight: Font.DemiBold
                    }

                    ListView {
                        id: files
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: jsonService.fileModel
                        spacing: Theme.px(4)

                        delegate: Rectangle {
                            id: fileRow
                            required property string name
                            required property string path
                            required property int layers
                            required property string modifiedLabel
                            required property int index

                            width: files.width
                            height: Theme.px(50)
                            radius: Theme.px(8)
                            color: jsonService.selectedPath === path ? Theme.primarySoft : (rowHover.hovered ? "#2eff82ba" : "transparent")
                            border.width: Math.max(1, Theme.px(1))
                            border.color: jsonService.selectedPath === path ? Theme.primary : Theme.border

                            Column {
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.leftMargin: Theme.px(10)
                                anchors.rightMargin: Theme.px(10)
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: Theme.px(2)

                                Text {
                                    width: parent.width
                                    text: fileRow.name
                                    color: Theme.text
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(11)
                                    elide: Text.ElideMiddle
                                }

                                Text {
                                    width: parent.width
                                    text: fileRow.layers + " layers  •  " + fileRow.modifiedLabel
                                    color: Theme.subtle
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(9.5)
                                    elide: Text.ElideRight
                                }
                            }

                            HoverHandler {
                                id: rowHover
                                cursorShape: Qt.PointingHandCursor
                            }

                            TapHandler {
                                onTapped: event => {
                                    event.accepted = true;
                                    jsonService.selectFile(fileRow.index);
                                }
                            }
                        }
                    }
                }
            }

            HoverCard {
                Layout.fillWidth: true
                Layout.minimumWidth: Theme.px(330)
                Layout.fillHeight: true
                padding: Theme.px(16)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(8)

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            text: "Preview / Inspector"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(13)
                            font.weight: Font.DemiBold
                        }

                        Item {
                            Layout.fillWidth: true
                        }

                        Text {
                            Layout.maximumWidth: parent.width * 0.42
                            text: transferService.status
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(10)
                            elide: Text.ElideRight
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        radius: Theme.px(10)
                        color: "#b408050b"
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.border

                        Image {
                            anchors.fill: parent
                            anchors.margins: Theme.px(10)
                            source: jsonService.previewUrl
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                        }

                        EmptyState {
                            visible: !jsonService.previewUrl
                            anchors.centerIn: parent
                            iconName: "json"
                            title: "Select a JSON"
                            message: "Choose a generation or folder, then a checkpoint."
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "Name: " + jsonService.selectedName
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                        elide: Text.ElideMiddle
                    }

                    Text {
                        text: "Layers: " + jsonService.selectedLayers
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "Folder: " + jsonService.selectedFolder
                        color: Theme.subtle
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.px(9.5)
                        elide: Text.ElideMiddle
                        ToolTip.visible: folderHover.hovered
                        ToolTip.text: jsonService.selectedFolder
                        HoverHandler {
                            id: folderHover
                        }
                    }
                }
            }
        }
    }

    Component {
        id: compactComponent

        GridLayout {
            columns: 3
            columnSpacing: Theme.px(8)

            HoverCard {
                Layout.preferredWidth: Theme.px(230)
                Layout.minimumWidth: Theme.px(205)
                Layout.fillHeight: true
                padding: Theme.px(14)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(8)

                    SectionHeading {
                        Layout.fillWidth: true
                        title: "JSON tools"
                        subtitle: "Compact browser"
                    }

                    KfpsComboBox {
                        id: compactGame
                        Layout.fillWidth: true
                        model: ["FH6", "FH5", "FM8"]
                    }

                    KfpsTextField {
                        id: compactLayers
                        Layout.fillWidth: true
                        text: "3000"
                        inputMethodHints: Qt.ImhDigitsOnly
                    }

                    KfpsComboBox {
                        id: compactSource
                        Layout.fillWidth: true
                        model: ["Generated finals", "Editor exports", "Exported game JSONs"]
                        onActivated: jsonService.setSource(currentIndex)
                    }

                    PrimaryButton {
                        Layout.fillWidth: true
                        text: "Import JSON"
                        enabled: jsonService.selectedPath.length > 0 && !transferService.running
                        onClicked: transferService.importJson(compactGame.currentText, jsonService.selectedPath, parseInt(compactLayers.text) || 0, true)
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        text: "Export group"
                        onClicked: transferService.exportJson(compactGame.currentText, parseInt(compactLayers.text) || 0)
                    }

                    Item {
                        Layout.fillHeight: true
                    }
                }
            }

            HoverCard {
                Layout.preferredWidth: Theme.px(280)
                Layout.minimumWidth: Theme.px(245)
                Layout.fillHeight: true
                padding: Theme.px(14)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(7)

                    Text {
                        text: "Folders"
                        color: Theme.primaryBright
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(13)
                        font.weight: Font.DemiBold
                    }

                    ListView {
                        id: compactGroups
                        Layout.fillWidth: true
                        Layout.preferredHeight: parent.height * 0.42
                        model: jsonService.groupModel
                        clip: true
                        spacing: Theme.px(4)

                        delegate: GhostButton {
                            required property string name
                            required property int index
                            width: compactGroups.width
                            minimumWidth: 0
                            text: name
                            onClicked: jsonService.selectGroup(index)
                        }
                    }

                    Text {
                        text: "JSON files"
                        color: Theme.primaryBright
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(13)
                        font.weight: Font.DemiBold
                    }

                    ListView {
                        id: compactFiles
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: jsonService.fileModel
                        clip: true
                        spacing: Theme.px(4)

                        delegate: GhostButton {
                            required property string name
                            required property int index
                            width: compactFiles.width
                            minimumWidth: 0
                            text: name
                            onClicked: jsonService.selectFile(index)
                        }
                    }
                }
            }

            HoverCard {
                Layout.fillWidth: true
                Layout.minimumWidth: Theme.px(250)
                Layout.fillHeight: true
                padding: Theme.px(14)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(8)

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        color: "#b408050b"
                        radius: Theme.px(10)
                        border.width: Math.max(1, Theme.px(1))
                        border.color: Theme.border

                        Image {
                            anchors.fill: parent
                            anchors.margins: Theme.px(8)
                            source: jsonService.previewUrl
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                        }

                        EmptyState {
                            visible: !jsonService.previewUrl
                            anchors.centerIn: parent
                            title: "Select a JSON"
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: jsonService.selectedName
                        color: Theme.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                        elide: Text.ElideMiddle
                    }

                    Text {
                        Layout.fillWidth: true
                        text: jsonService.selectedFolder
                        color: Theme.subtle
                        font.family: Theme.monoFamily
                        font.pixelSize: Theme.px(9)
                        elide: Text.ElideMiddle
                    }
                }
            }
        }
    }
}
