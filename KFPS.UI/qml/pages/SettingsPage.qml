import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent

    ScrollView {
        id: scroll
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            spacing: Theme.px(12)

            SectionHeading {
                Layout.fillWidth: true
                title: "Checks and preferences"
                subtitle: "The packaged app includes its own Python runtime and backend dependencies. Settings verifies that bundle and controls the native QML interface."
            }

            GridLayout {
                Layout.fillWidth: true
                columns: Theme.logical(root.width) > 900 ? 2 : 1
                columnSpacing: Theme.px(12)
                rowSpacing: Theme.px(12)

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(360)
                    padding: Theme.px(18)

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.px(10)

                        Text {
                            text: "Bundle checks"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(16)
                            font.weight: Font.DemiBold
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "A complete release should not require a separate Python installation."
                            color: Theme.muted
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(11)
                            wrapMode: Text.Wrap
                        }

                        StatusRow {
                            Layout.fillWidth: true
                            label: "Python 3.12"
                            value: runtimeService.pythonText
                            state: runtimeService.ready ? "ok" : "warn"
                        }

                        StatusRow {
                            Layout.fillWidth: true
                            label: "Dependencies"
                            value: runtimeService.dependenciesText
                            state: runtimeService.ready ? "ok" : "warn"
                        }

                        StatusRow {
                            Layout.fillWidth: true
                            label: "Runtime"
                            value: runtimeService.runtimeText
                            state: runtimeService.ready ? "ok" : "warn"
                        }

                        Item {
                            Layout.fillHeight: true
                        }

                        PrimaryButton {
                            Layout.fillWidth: true
                            text: runtimeService.checking ? "Checking…" : "Run bundle checks"
                            iconName: "check"
                            enabled: !runtimeService.checking
                            onClicked: runtimeService.check()
                        }

                        GhostButton {
                            Layout.fillWidth: true
                            text: "Open runtime folder"
                            iconName: "folder"
                            onClicked: desktop.openRuntime()
                        }
                    }
                }

                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.px(360)
                    padding: Theme.px(18)

                    ColumnLayout {
                        anchors.fill: parent
                        spacing: Theme.px(10)

                        Text {
                            text: "Interface"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(16)
                            font.weight: Font.DemiBold
                        }

                        Label {
                            text: "Theme preset"
                        }

                        KfpsComboBox {
                            Layout.fillWidth: true
                            model: ["Night Blossom"]
                            currentIndex: 0
                            enabled: true
                        }

                        Label {
                            text: "UI scale  •  " + Math.round(settings.uiScale * 100) + "%"
                        }

                        KfpsSlider {
                            Layout.fillWidth: true
                            from: 0.8
                            to: 1.35
                            stepSize: 0.05
                            value: settings.uiScale
                            onMoved: settings.uiScale = value
                        }

                        KfpsSwitch {
                            Layout.fillWidth: true
                            text: "Enable manual generator overrides"
                            checked: settings.manualOverrides
                            onToggled: settings.manualOverrides = checked
                        }

                        KfpsSwitch {
                            Layout.fillWidth: true
                            text: "Reduce nonessential motion"
                            checked: settings.reducedMotion
                            onToggled: settings.reducedMotion = checked
                        }

                        KfpsSwitch {
                            Layout.fillWidth: true
                            text: "Ambient branch and petals"
                            checked: settings.ambientMotion
                            enabled: !settings.reducedMotion
                            onToggled: settings.ambientMotion = checked
                        }

                        KfpsSwitch {
                            Layout.fillWidth: true
                            text: "Glass shadows and effects"
                            checked: settings.glassEffects
                            onToggled: settings.glassEffects = checked
                        }
                    }
                }
            }

            HoverCard {
                id: rootCard
                Layout.fillWidth: true
                Layout.preferredHeight: Theme.px(185)
                padding: Theme.px(18)

                ColumnLayout {
                    anchors.fill: parent
                    spacing: Theme.px(10)

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            text: "Current app root"
                            color: Theme.primaryBright
                            font.family: Theme.fontFamily
                            font.pixelSize: Theme.px(15)
                            font.weight: Font.DemiBold
                        }

                        Item {
                            Layout.fillWidth: true
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: Theme.logical(rootCard.width) > 650 ? 3 : 1
                        columnSpacing: Theme.px(8)
                        rowSpacing: Theme.px(8)

                        GhostButton {
                            Layout.fillWidth: true
                            text: "Open root"
                            iconName: "folder"
                            onClicked: desktop.openRoot()
                        }

                        GhostButton {
                            Layout.fillWidth: true
                            text: "JSON folders"
                            onClicked: desktop.openJsonFolders()
                        }

                        GhostButton {
                            Layout.fillWidth: true
                            text: "Generated"
                            onClicked: desktop.openGenerated()
                        }
                    }

                    KfpsTextField {
                        Layout.fillWidth: true
                        text: "The current KFPS application root is shown in runtime logs at startup."
                        readOnly: true
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "Theme infrastructure is ready for future presets, but Night Blossom is the only selectable theme in this release."
                        color: Theme.muted
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.px(11)
                        wrapMode: Text.Wrap
                    }
                }
            }
        }
    }
}
