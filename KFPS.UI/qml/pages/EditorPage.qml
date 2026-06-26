import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root

    anchors.fill: parent
    property bool wide: Theme.logical(width) >= 980

    Loader {
        anchors.fill: parent
        sourceComponent: root.wide ? wideComponent : compactComponent
    }

    Component {
        id: launchPanel

        ColumnLayout {
            spacing: Theme.px(10)

            SectionHeading {
                Layout.fillWidth: true
                title: "Launch and projects"
                subtitle: "The Fabric editor remains the existing local browser app."
            }

            PrimaryButton {
                Layout.fillWidth: true
                text: "Open Editor"
                iconName: "editor"
                onClicked: editorService.launch()
            }

            GhostButton {
                Layout.fillWidth: true
                text: "Refresh project browser"
                iconName: "refresh"
                onClicked: editorService.refresh()
            }

            GhostButton {
                Layout.fillWidth: true
                text: "Projects folder"
                iconName: "folder"
                onClicked: editorService.openProjects()
            }

            GhostButton {
                Layout.fillWidth: true
                text: "Editor app folder"
                onClicked: editorService.openEditorFolder()
            }

            GlassPanel {
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.px(130)
                soft: true

                Column {
                    anchors.fill: parent
                    anchors.margins: Theme.px(12)
                    spacing: Theme.px(7)

                    Text {
                        text: "Project files vs exports"
                        color: Theme.primaryBright
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(13)
                        font.weight: Font.DemiBold
                    }

                    Text {
                        width: parent.width
                        text: "Projects preserve editor state and overlays. Exported JSONs are the files intended for the JSON import workflow."
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                        wrapMode: Text.Wrap
                        lineHeight: 1.28
                    }
                }
            }

            Item {
                Layout.fillHeight: true
            }
        }
    }

    Component {
        id: projectBrowserPanel

        ColumnLayout {
            spacing: Theme.px(8)

            Text {
                text: "Project browser"
                color: Theme.primaryBright
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(14)
                font.weight: Font.DemiBold
            }

            ListView {
                id: projects
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: editorService.projectModel
                spacing: Theme.px(5)

                delegate: GhostButton {
                    required property string name
                    required property string modifiedLabel
                    required property int index
                    width: projects.width
                    minimumWidth: 0
                    text: name + "  •  " + modifiedLabel
                    onClicked: editorService.select(index)
                }
            }
        }
    }

    Component {
        id: previewPanel

        ColumnLayout {
            id: previewRoot
            spacing: Theme.px(10)
            property bool compactActions: Theme.logical(width) < 520

            SectionHeading {
                Layout.fillWidth: true
                title: editorService.selectedName === "—" ? "Project preview" : editorService.selectedName
                subtitle: editorService.selectedPath || "Select a project from the browser."
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: Theme.px(180)
                radius: Theme.px(10)
                color: "#b408050b"
                border.width: Math.max(1, Theme.px(1))
                border.color: Theme.border

                Image {
                    anchors.fill: parent
                    anchors.margins: Theme.px(10)
                    source: editorService.previewUrl
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                }

                EmptyState {
                    visible: !editorService.previewUrl
                    anchors.centerIn: parent
                    iconName: "editor"
                    title: "Select a project"
                    message: "A rendered preview will appear here."
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.px(6)

                Text {
                    Layout.fillWidth: true
                    text: "Shapes: " + editorService.selectedShapes
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(11)
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }

                GridLayout {
                    Layout.fillWidth: true
                    columns: previewRoot.compactActions ? 1 : 2
                    columnSpacing: Theme.px(8)
                    rowSpacing: Theme.px(6)

                    PrimaryButton {
                        Layout.fillWidth: true
                        minimumWidth: 0
                        text: "Use selected project in editor"
                        maximumTextWidth: Theme.px(220)
                        enabled: editorService.selectedPath.length > 0
                        onClicked: editorService.launchSelected()
                    }

                    GhostButton {
                        Layout.fillWidth: true
                        minimumWidth: 0
                        text: "Open projects folder"
                        maximumTextWidth: Theme.px(170)
                        onClicked: editorService.openProjects()
                    }
                }
            }
        }
    }

    Component {
        id: wideComponent

        GridLayout {
            columns: 3
            columnSpacing: Theme.px(10)

            HoverCard {
                Layout.preferredWidth: Theme.px(270)
                Layout.minimumWidth: Theme.px(240)
                Layout.fillHeight: true
                padding: Theme.px(16)
                Loader {
                    anchors.fill: parent
                    sourceComponent: launchPanel
                }
            }

            HoverCard {
                Layout.preferredWidth: Theme.px(320)
                Layout.minimumWidth: Theme.px(260)
                Layout.fillHeight: true
                padding: Theme.px(14)
                Loader {
                    anchors.fill: parent
                    sourceComponent: projectBrowserPanel
                }
            }

            HoverCard {
                Layout.fillWidth: true
                Layout.minimumWidth: Theme.px(350)
                Layout.fillHeight: true
                padding: Theme.px(16)
                Loader {
                    anchors.fill: parent
                    sourceComponent: previewPanel
                }
            }
        }
    }

    Component {
        id: compactComponent

        ScrollView {
            id: compactScroll
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: compactScroll.availableWidth
                spacing: Theme.px(10)

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(390)
                    padding: Theme.px(16)
                    Loader {
                        anchors.fill: parent
                        sourceComponent: launchPanel
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(320)
                    padding: Theme.px(14)
                    Loader {
                        anchors.fill: parent
                        sourceComponent: projectBrowserPanel
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(500)
                    padding: Theme.px(16)
                    Loader {
                        anchors.fill: parent
                        sourceComponent: previewPanel
                    }
                }
            }
        }
    }
}
