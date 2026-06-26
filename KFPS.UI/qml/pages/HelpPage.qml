import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    anchors.fill: parent
    property bool wide: Theme.logical(width) >= 850

    Loader {
        anchors.fill: parent
        sourceComponent: root.wide ? wideComponent : compactComponent
    }

    Component {
        id: topicListComponent
        ColumnLayout {
            spacing: Theme.px(8)
            SectionHeading {
                Layout.fillWidth: true
                title: "Help topics"
                subtitle: "Plain-language guidance for the complete KFPS workflow."
            }
            KfpsTextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: "Search help…"
                onTextChanged: helpService.search(text)
            }
            ListView {
                id: topicsList
                Layout.fillWidth: true
                Layout.fillHeight: true
                model: helpService.topicModel
                clip: true
                spacing: Theme.px(5)
                delegate: GhostButton {
                    width: topicsList.width
                    height: Theme.px(46)
                    minimumWidth: 0
                    text: title
                    accentText: index === topicsList.currentIndex
                    onClicked: {
                        topicsList.currentIndex = index;
                        helpService.select(index);
                    }
                }
            }
            GhostButton {
                Layout.fillWidth: true
                text: "Open Nexus Mods page"
                iconName: "external"
                onClicked: desktop.openUrl("https://www.nexusmods.com/forzahorizon6/mods/214")
            }
        }
    }

    Component {
        id: articleComponent
        ColumnLayout {
            spacing: Theme.px(10)
            SectionHeading {
                Layout.fillWidth: true
                title: helpService.title
                subtitle: helpService.summary
            }
            Rectangle {
                Layout.fillWidth: true
                height: Math.max(1, Theme.px(1))
                color: Theme.borderSoft
            }
            ScrollView {
                id: articleScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                Column {
                    id: sectionsColumn
                    width: articleScroll.availableWidth
                    spacing: Theme.px(12)
                    property var sectionData: helpService.sections

                    Repeater {
                        model: sectionsColumn.sectionData.length
                        delegate: GlassPanel {
                            required property int index
                            width: sectionsColumn.width
                            height: sectionContent.implicitHeight + Theme.px(28)
                            soft: true
                            property var section: sectionsColumn.sectionData[index]

                            Column {
                                id: sectionContent
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: Theme.px(14)
                                spacing: Theme.px(7)
                                Text {
                                    width: parent.width
                                    text: section ? section.heading : ""
                                    color: Theme.primaryBright
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(14)
                                    font.weight: Font.DemiBold
                                    wrapMode: Text.Wrap
                                }
                                Text {
                                    width: parent.width
                                    text: section ? section.body : ""
                                    color: Theme.muted
                                    font.family: Theme.fontFamily
                                    font.pixelSize: Theme.px(11.5)
                                    wrapMode: Text.Wrap
                                    lineHeight: 1.38
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: wideComponent
        GridLayout {
            columns: 2
            columnSpacing: Theme.px(10)
            HoverCard {
                Layout.preferredWidth: Theme.px(300)
                Layout.fillHeight: true
                padding: Theme.px(16)
                Loader {
                    anchors.fill: parent
                    sourceComponent: topicListComponent
                }
            }
            HoverCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: Theme.px(18)
                Loader {
                    anchors.fill: parent
                    sourceComponent: articleComponent
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
                    Layout.preferredHeight: Theme.px(315)
                    padding: Theme.px(16)
                    Loader {
                        anchors.fill: parent
                        sourceComponent: topicListComponent
                    }
                }
                HoverCard {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(Theme.px(520), articleLoader.item ? articleLoader.item.implicitHeight : 0)
                    padding: Theme.px(16)
                    Loader {
                        id: articleLoader
                        anchors.fill: parent
                        sourceComponent: articleComponent
                    }
                }
            }
        }
    }
}
