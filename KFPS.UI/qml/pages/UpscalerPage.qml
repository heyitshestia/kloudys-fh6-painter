import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    objectName: "UpscalerPage"
    readonly property var dataView: upscaleService.view
    property bool advancedOpen: false
    property real comparePosition: 0.5

    component ScaleTab: TabButton {
        required property int factor
        objectName: "UpscalerScale" + factor
        text: factor + "x"
        onClicked: upscaleService.configure("scale", factor)
        ToolTip.visible: hovered
        ToolTip.text: "Scale width and height by " + factor + "."
        contentItem: Text {
            text: parent.text
            color: parent.checked ? Theme.surface : Theme.text
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            font.family: Theme.fontFamily
            font.pixelSize: Theme.px(12)
        }
        background: Rectangle {
            color: parent.checked ? Theme.primaryBright : Theme.surfaceRaised
            border.color: Theme.border
            radius: Theme.corner(Theme.px(3))
        }
    }

    FastScrollView {
        id: scroll
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true
        ColumnLayout {
            width: scroll.availableWidth
            spacing: Theme.px(12)
            RowLayout {
                Layout.fillWidth: true
                GhostButton {
                    objectName: "UpscalerBack"
                    text: "Tools"
                    toolTipText: "Return to Tools. An active upscale continues in the background."
                    onClicked: appController.navigate("tools")
                }
                Text {
                    Layout.fillWidth: true
                    text: "Image Upscaler"
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.px(22)
                    font.bold: true
                }
                Text {
                    text: "LOCAL"
                    color: Theme.primaryBright
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10)
                }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: Theme.logical(root.width) < 800 ? 1 : 2
                columnSpacing: Theme.px(16)
                rowSpacing: Theme.px(10)
                RowLayout {
                    Layout.fillWidth: true
                    PrimaryButton {
                        objectName: "UpscalerChoose"
                        text: "Open image"
                        iconName: "folder"
                        enabled: !root.dataView.busy
                        toolTipText: "Choose a PNG, JPEG, WebP or BMP to upscale locally."
                        onClicked: upscaleService.choose()
                    }
                    GhostButton {
                        text: "Current source"
                        enabled: !root.dataView.busy && sourceService.path.length > 0
                        toolTipText: "Load the image currently selected for generation."
                        onClicked: upscaleService.useCurrentSource()
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: "Preset"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(12) }
                    KfpsComboBox {
                        objectName: "UpscalerPreset"
                        Layout.fillWidth: true
                        model: ["Photo", "Anime", "Text & Logo"]
                        currentIndex: ["photo", "anime", "text"].indexOf(root.dataView.preset)
                        enabled: !root.dataView.busy
                        toolTipText: "Select a model preset and reset its recommended noise, GPU and tile settings."
                        onActivated: upscaleService.configure("preset", ["photo", "anime", "text"][currentIndex])
                    }
                    TabBar {
                        objectName: "UpscalerScale"
                        Layout.preferredWidth: Theme.px(120)
                        enabled: !root.dataView.busy
                        currentIndex: root.dataView.scale === 4 ? 1 : 0
                        ScaleTab { factor: 2 }
                        ScaleTab { factor: 4 }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                text: "Recommended: " + root.dataView.recommendation
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(11)
                wrapMode: Text.Wrap
            }
            GridLayout {
                objectName: "UpscalerActions"
                Layout.fillWidth: true
                columns: Theme.logical(root.width) < 800 ? 3 : 5
                rowSpacing: Theme.px(8)
                columnSpacing: Theme.px(8)
                PrimaryButton {
                    objectName: "UpscalerStart"
                    text: root.dataView.engineReady ? "Upscale" : "Download & upscale"
                    iconName: "upscale"
                    enabled: !root.dataView.busy && root.dataView.source.length > 0 && root.dataView.available
                    toolTipText: "Create a new upscaled PNG locally. The original is never overwritten."
                    onClicked: upscaleService.start()
                }
                GhostButton {
                    objectName: "UpscalerCancel"
                    text: "Cancel"
                    enabled: root.dataView.busy && root.dataView.operation === "upscale"
                    toolTipText: "Stop the download or native GPU job without changing the source image."
                    onClicked: upscaleService.cancel()
                }
                GhostButton {
                    objectName: "UpscalerUseResult"
                    text: "Use as source"
                    enabled: !root.dataView.busy && root.dataView.output.length > 0
                    toolTipText: "Select the completed PNG for generation and return to Create."
                    onClicked: { upscaleService.useResult(); appController.navigate("create") }
                }
                GhostButton {
                    text: "Save as"
                    enabled: !root.dataView.busy && root.dataView.output.length > 0
                    toolTipText: "Save a copy of the completed PNG to another location."
                    onClicked: upscaleService.saveAs()
                }
                GhostButton {
                    text: "Open folder"
                    iconName: "folder"
                    enabled: root.dataView.output.length > 0
                    toolTipText: "Open the folder containing the completed upscaled image."
                    onClicked: upscaleService.openOutputFolder()
                }
            }
            Text {
                Layout.fillWidth: true
                visible: !root.dataView.engineReady
                text: root.dataView.available ? "First use: " + root.dataView.downloadMB + " MB engine download from GitHub. Image stays local." : "Upscaler files are missing. Repair KFPS before continuing."
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(11)
                wrapMode: Text.Wrap
            }
            ProgressBar {
                Layout.fillWidth: true
                visible: root.dataView.busy
                from: 0; to: 100
                value: root.dataView.progress
                indeterminate: root.dataView.progress < 0
            }
            Text {
                objectName: "UpscalerStatus"
                Layout.fillWidth: true
                text: root.dataView.error || root.dataView.status
                color: root.dataView.error ? Theme.danger : Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(12)
                wrapMode: Text.Wrap
            }
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: root.dataView.sourceName + (root.dataView.sourceSize ? " | " + root.dataView.sourceSize : "")
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(12)
                    elide: Text.ElideMiddle
                }
                Text {
                    text: root.dataView.output ? root.dataView.outputName : root.dataView.targetSize
                    Layout.maximumWidth: preview.width * 0.48
                    elide: Text.ElideRight
                    color: Theme.primaryBright
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(11)
                }
            }
            Rectangle {
                id: preview
                objectName: "UpscalerPreview"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(Theme.px(240), Math.min(Theme.px(390), root.height - Theme.px(370)))
                color: Theme.surface
                border.color: Theme.border
                clip: true
                ArtworkPreviewBackdrop { anchors.fill: parent }
                Image {
                    anchors.fill: parent
                    anchors.margins: Theme.px(12)
                    source: root.visible ? (root.dataView.outputUrl || root.dataView.sourceUrl) : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: false
                }
                Item {
                    width: parent.width * (root.dataView.output ? root.comparePosition : 1)
                    height: parent.height
                    clip: true
                    ArtworkPreviewBackdrop { width: preview.width; height: preview.height }
                    Image {
                        x: Theme.px(12); y: Theme.px(12)
                        width: preview.width - Theme.px(24)
                        height: preview.height - Theme.px(24)
                        source: root.visible ? root.dataView.sourceUrl : ""
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: false
                    }
                }
                Rectangle {
                    visible: root.dataView.output.length > 0
                    x: preview.width * root.comparePosition
                    height: parent.height
                    width: Theme.px(2)
                    color: Theme.primaryBright
                }
                Text {
                    anchors.left: parent.left; anchors.top: parent.top; anchors.margins: Theme.px(12)
                    text: root.dataView.source ? "Original" : "No image selected"
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(11)
                }
                Text {
                    anchors.right: parent.right; anchors.top: parent.top; anchors.margins: Theme.px(12)
                    visible: root.dataView.output.length > 0
                    text: "Upscaled"
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(11)
                }
                DropArea {
                    anchors.fill: parent
                    enabled: !root.dataView.busy
                    onDropped: function(drop) {
                        if (drop.hasUrls && drop.urls.length === 1) {
                            upscaleService.setSource(drop.urls[0])
                            drop.acceptProposedAction()
                        }
                    }
                }
            }
            KfpsSlider {
                objectName: "UpscalerCompare"
                Layout.fillWidth: true
                visible: root.dataView.output.length > 0
                from: 0; to: 1; value: root.comparePosition
                toolTipText: "Move the divider between the original and upscaled previews."
                onMoved: root.comparePosition = value
            }
            RowLayout {
                Layout.fillWidth: true
                KfpsSwitch {
                    objectName: "UpscalerAdvanced"
                    text: "Advanced"
                    checked: root.advancedOpen
                    toolTipText: "Show GPU, memory and model quality controls."
                    onToggled: root.advancedOpen = checked
                }
                Text {
                    Layout.fillWidth: true
                    text: root.dataView.settingsLabel
                    color: Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(11)
                    wrapMode: Text.Wrap
                }
            }
            GridLayout {
                objectName: "UpscalerAdvancedControls"
                Layout.fillWidth: true
                visible: root.advancedOpen
                enabled: !root.dataView.busy
                columns: Theme.logical(root.width) < 800 ? 2 : 4
                columnSpacing: Theme.px(12)
                rowSpacing: Theme.px(8)
                Text { text: "Noise removal"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(11) }
                KfpsComboBox {
                    objectName: "UpscalerNoise"
                    Layout.fillWidth: true
                    enabled: root.dataView.engine === "waifu2x"
                    model: ["Off", "Light", "Medium", "Strong", "Maximum"]
                    currentIndex: root.dataView.noise + 1
                    toolTipText: "Stronger waifu2x denoising can remove compression artifacts but may soften lettering."
                    onActivated: upscaleService.configure("noise", currentIndex - 1)
                }
                Text { text: "Tile size"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(11) }
                KfpsComboBox {
                    Layout.fillWidth: true
                    model: ["32 px", "64 px", "128 px", "256 px"]
                    currentIndex: [32, 64, 128, 256].indexOf(root.dataView.tile)
                    toolTipText: "Smaller tiles reduce GPU memory requirements at the cost of processing speed."
                    onActivated: upscaleService.configure("tile", [32, 64, 128, 256][currentIndex])
                }
                Text { text: "GPU"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(11) }
                KfpsComboBox {
                    Layout.fillWidth: true
                    model: ["Auto", "GPU 0", "GPU 1", "GPU 2", "GPU 3"]
                    currentIndex: ["auto", "0", "1", "2", "3"].indexOf(root.dataView.gpu)
                    toolTipText: "Use automatic GPU selection unless a specific adapter is needed. GPU details are recorded in the run log."
                    onActivated: upscaleService.configure("gpu", ["auto", "0", "1", "2", "3"][currentIndex])
                }
                KfpsCheckBox {
                    text: "Enhanced quality"
                    checked: root.dataView.tta
                    toolTipText: "Average multiple transformed passes. Much slower; improvements depend on the image."
                    onToggled: upscaleService.configure("tta", checked)
                }
                GhostButton {
                    text: "Reset preset"
                    toolTipText: "Restore the recommended settings for the selected preset."
                    onClicked: upscaleService.configure("reset", true)
                }
            }
            GhostButton {
                visible: root.dataView.report.length > 0
                text: "Run report"
                toolTipText: "Open the settings, timings, result and native GPU log for this run."
                onClicked: upscaleService.openReport()
            }
        }
    }
}
