import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Item {
    id: root
    objectName: "BackgroundRemoverPage"
    readonly property var dataView: backgroundRemoveService.view
    property bool advancedOpen: false
    property alias comparePosition: preview.comparePosition
    property real areaTolerance: 20
    Connections {
        target: backgroundRemoveService
        function onResultReady() { appController.navigate("create") }
    }
    Shortcut {
        sequence: StandardKey.Undo
        enabled: root.visible && root.dataView.canUndo && !root.dataView.busy && !preview.drawing
        onActivated: backgroundRemoveService.history(-1)
    }
    Shortcut {
        sequence: StandardKey.Redo
        enabled: root.visible && root.dataView.canRedo && !root.dataView.busy && !preview.drawing
        onActivated: backgroundRemoveService.history(1)
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
                    text: "Tools"
                    toolTipText: "Return to Tools. Active processing continues in the background."
                    onClicked: appController.navigate("tools")
                }
                Text {
                    Layout.fillWidth: true
                    text: "Background Remover"
                    color: Theme.text
                    font.family: Theme.displayFamily
                    font.pixelSize: Theme.px(22)
                    font.bold: true
                    wrapMode: Text.Wrap
                }
                Text {
                    text: "LOCAL CPU"
                    color: Theme.primaryBright
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(10)
                }
            }
            RowLayout {
                Layout.fillWidth: true
                PrimaryButton {
                    objectName: "BackgroundRemoverChoose"
                    text: "Open image"
                    iconName: "folder"
                    enabled: !root.dataView.busy
                    toolTipText: "Choose a PNG, JPEG, WebP or BMP. The original is never overwritten."
                    onClicked: backgroundRemoveService.choose()
                }
                GhostButton {
                    text: "Current source"
                    enabled: !root.dataView.busy && sourceService.path.length > 0
                    toolTipText: "Load the image currently selected for generation."
                    onClicked: backgroundRemoveService.useCurrentSource()
                }
                Item { Layout.fillWidth: true }
                GhostButton {
                    objectName: "BackgroundRemoverResume"
                    text: "Resume last"
                    visible: root.dataView.resumeAvailable
                    enabled: !root.dataView.busy
                    toolTipText: "Reopen the last saved cutout and its correction history."
                    onClicked: backgroundRemoveService.resume()
                }
            }
            RowLayout {
                Layout.fillWidth: true
                KfpsComboBox {
                    objectName: "BackgroundRemoverMode"
                    Layout.fillWidth: true
                    Layout.maximumWidth: Theme.px(320)
                    model: ["Illustration (refined)", "Anime (soft edges)", "Logo / flat colour"]
                    currentIndex: ["illustration", "anime", "color"].indexOf(root.dataView.mode)
                    enabled: !root.dataView.busy
                    toolTipText: "Refined illustration clears uncertain background gaps. Soft edges preserves more delicate transparency. Logo removes a selected background colour."
                    onActivated: backgroundRemoveService.configure("mode", ["illustration", "anime", "color"][currentIndex])
                }
                Rectangle {
                    visible: root.dataView.mode === "color"
                    Layout.preferredWidth: Theme.px(30); Layout.preferredHeight: Theme.px(30)
                    color: root.dataView.color === "auto" ? root.dataView.detectedColor : root.dataView.color
                    border.color: Theme.border
                }
                BackgroundToolButton {
                    objectName: "BackgroundRemoverPickColor"
                    visible: root.dataView.mode === "color"
                    glyph: "pipette"; help: "Pick background colour from the original"
                    enabled: !root.dataView.busy && root.dataView.source.length > 0
                    checkable: true; checked: preview.tool === "pick"
                    onClicked: preview.tool=checked ? "pick" : "pan"
                }
                GhostButton {
                    visible: root.dataView.mode === "color"
                    text: "Auto colour"
                    toolTipText: "Use the most common opaque colour along the original image border."
                    enabled: !root.dataView.busy
                    onClicked: backgroundRemoveService.configure("color", "auto")
                }
                Item { Layout.fillWidth: true }
            }
            RowLayout {
                visible: root.dataView.mode === "color"
                Layout.fillWidth: true
                Text { text: "Tolerance"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(12) }
                KfpsSlider {
                    objectName: "BackgroundRemoverTolerance"
                    Layout.fillWidth: true
                    from: 0; to: 100; stepSize: 1; value: root.dataView.tolerance
                    enabled: !root.dataView.busy
                    toolTipText: "Colour difference accepted as background. Lower values preserve more similar-coloured details."
                    onMoved: backgroundRemoveService.configure("tolerance", value)
                }
                Text { text: root.dataView.tolerance; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.px(12); Layout.preferredWidth: Theme.px(30) }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: Theme.logical(root.width) < 800 ? 3 : 5
                rowSpacing: Theme.px(8)
                columnSpacing: Theme.px(8)
                PrimaryButton {
                    objectName: "BackgroundRemoverStart"
                    text: root.dataView.preserveOnly ? "Keep transparency" : (root.dataView.engineReady ? "Remove background" : "Download & remove")
                    iconName: "cutout"
                    enabled: !root.dataView.busy && root.dataView.source.length > 0 && root.dataView.available
                    toolTipText: "Create a new local cutout with the selected mode. Review the result before using it."
                    onClicked: backgroundRemoveService.start()
                }
                GhostButton {
                    objectName: "BackgroundRemoverCancel"
                    text: "Cancel"
                    enabled: root.dataView.busy && root.dataView.operation === "remove"
                    toolTipText: "Stop the download or CPU worker. Your original remains unchanged."
                    onClicked: backgroundRemoveService.cancel()
                }
                GhostButton {
                    objectName: "BackgroundRemoverUseResult"
                    text: "Use as source"
                    enabled: !root.dataView.busy && root.dataView.output.length > 0
                    toolTipText: "Select the completed PNG for generation and return to Create."
                    onClicked: backgroundRemoveService.useResult()
                }
                GhostButton {
                    objectName: "BackgroundRemoverSaveAs"
                    text: "Save PNG"
                    enabled: !root.dataView.busy && root.dataView.output.length > 0
                    toolTipText: "Save a copy of the completed PNG."
                    onClicked: backgroundRemoveService.saveAs()
                }
                GhostButton {
                    text: "Open folder"
                    iconName: "folder"
                    enabled: root.dataView.output.length > 0
                    toolTipText: "Open the folder containing the completed PNG."
                    onClicked: backgroundRemoveService.openOutputFolder()
                }
            }
            Text {
                Layout.fillWidth: true
                visible: !root.dataView.engineReady && !root.dataView.preserveOnly
                text: root.dataView.available ? "First use: " + root.dataView.downloadMB + " MB download from GitHub and PyPI. Image stays local." : "Engine catalog missing. Repair KFPS before continuing."
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(11)
                wrapMode: Text.Wrap
            }
            Text {
                objectName: "BackgroundRemoverWarning"
                Layout.fillWidth: true
                visible: root.dataView.warning.length > 0
                text: root.dataView.warning
                color: Theme.danger
                font.family: Theme.fontFamily
                font.pixelSize: Theme.px(12)
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
                objectName: "BackgroundRemoverStatus"
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
                    text: root.dataView.outputName
                    Layout.maximumWidth: preview.width * 0.45
                    color: Theme.primaryBright
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.px(11)
                    elide: Text.ElideRight
                }
            }
            Flow {
                Layout.fillWidth: true
                spacing: Theme.px(4)
                BackgroundToolButton {
                    objectName: "BackgroundRemoverPan"
                    glyph: "hand"; help: "Pan image"
                    checkable: true; checked: preview.tool === "pan"
                    onClicked: preview.tool="pan"
                }
                BackgroundToolButton {
                    objectName: "BackgroundRemoverErase"
                    glyph: "eraser"; help: "Erase brush"
                    enabled: root.dataView.editable && !root.dataView.busy
                    checkable: true; checked: preview.tool === "erase"
                    onClicked: preview.tool="erase"
                }
                BackgroundToolButton {
                    objectName: "BackgroundRemoverRestore"
                    glyph: "brush"; help: "Restore original brush"
                    enabled: root.dataView.editable && !root.dataView.busy
                    checkable: true; checked: preview.tool === "restore"
                    onClicked: preview.tool="restore"
                }
                BackgroundToolButton {
                    objectName: "BackgroundRemoverWand"
                    glyph: "wand-sparkles"; help: "Erase connected colour area"
                    enabled: root.dataView.editable && !root.dataView.busy
                    checkable: true; checked: preview.tool === "wand"
                    onClicked: preview.tool="wand"
                }
                BackgroundToolButton {
                    objectName: "BackgroundRemoverUndo"
                    glyph: "undo-2"; help: "Undo correction"
                    enabled: root.dataView.canUndo && !root.dataView.busy && !preview.drawing
                    onClicked: backgroundRemoveService.history(-1)
                }
                BackgroundToolButton {
                    objectName: "BackgroundRemoverRedo"
                    glyph: "redo-2"; help: "Redo correction"
                    enabled: root.dataView.canRedo && !root.dataView.busy && !preview.drawing
                    onClicked: backgroundRemoveService.history(1)
                }
                BackgroundToolButton {
                    glyph: "zoom-out"; help: "Zoom out"
                    enabled: preview.zoom > 1
                    onClicked: preview.zoomBy(1/1.4,preview.width/2,preview.height/2)
                }
                BackgroundToolButton {
                    glyph: "zoom-in"; help: "Zoom in"
                    enabled: preview.zoom < 12
                    onClicked: preview.zoomBy(1.4,preview.width/2,preview.height/2)
                }
                BackgroundToolButton {
                    objectName: "BackgroundRemoverFit"
                    glyph: "maximize"; help: "Fit image"
                    onClicked: preview.fit()
                }
                KfpsComboBox {
                    objectName: "BackgroundRemoverViewMode"
                    width: Theme.px(140)
                    model: ["Compare", "Result", "Original", "Mask"]
                    toolTipText: "Choose the before-and-after comparison, cutout, original image or transparency mask."
                    currentIndex: preview.viewMode
                    onActivated: { preview.viewMode=currentIndex; preview.tool="pan" }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                visible: preview.tool === "erase" || preview.tool === "restore" || preview.tool === "wand"
                Text {
                    text: preview.tool === "wand" ? "Area tolerance" : "Brush size"
                    color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(12)
                }
                KfpsSlider {
                    objectName: "BackgroundRemoverBrushSize"
                    toolTipText: preview.tool === "wand" ? "Connected-area colour tolerance. Lower values preserve more similar colours." : "Brush diameter in original image pixels, independent of zoom."
                    Layout.fillWidth: true
                    from: preview.tool === "wand" ? 0 : 2
                    to: preview.tool === "wand" ? 100 : 400
                    stepSize: 1
                    value: preview.tool === "wand" ? root.areaTolerance : preview.brushSize
                    onMoved: { if (preview.tool === "wand") root.areaTolerance=value; else preview.brushSize=value }
                }
                Text {
                    text: Math.round(preview.tool === "wand" ? root.areaTolerance : preview.brushSize)
                    Layout.preferredWidth: Theme.px(35)
                    color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: Theme.px(12)
                }
            }
            BackgroundMaskPreview {
                id: preview
                objectName: "BackgroundRemoverPreview"
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(Theme.px(300), Math.min(Theme.px(600), root.height - Theme.px(300)))
                sourceUrl: root.visible ? root.dataView.sourceUrl : ""
                outputUrl: root.visible ? root.dataView.outputUrl : ""
                maskUrl: root.visible ? root.dataView.maskUrl : ""
                imageWidth: root.dataView.width
                imageHeight: root.dataView.height
                busy: root.dataView.busy
                editable: root.dataView.editable
                onCorrected: function(tool, points, diameter) { backgroundRemoveService.correct(tool,points,diameter,root.areaTolerance) }
                onSampled: function(x,y) { backgroundRemoveService.sampleColor(x,y); preview.tool="pan" }
                onDropped: function(url) { backgroundRemoveService.setSource(url) }
            }
            KfpsSlider {
                objectName: "BackgroundRemoverCompare"
                Layout.fillWidth: true
                visible: root.dataView.output.length > 0 && preview.viewMode === 0
                from: 0; to: 1; value: root.comparePosition
                toolTipText: "Compare the original with the transparent result."
                onMoved: root.comparePosition = value
            }
            KfpsSwitch {
                objectName: "BackgroundRemoverAdvanced"
                text: "Advanced"
                checked: root.advancedOpen
                toolTipText: "Show transparency refinement, island cleanup and CPU controls."
                onToggled: root.advancedOpen = checked
            }
            GridLayout {
                Layout.fillWidth: true
                visible: root.advancedOpen
                enabled: !root.dataView.busy
                columns: Theme.logical(root.width) < 800 ? 1 : 2
                columnSpacing: Theme.px(12)
                rowSpacing: Theme.px(8)
                KfpsCheckBox {
                    objectName: "BackgroundRemoverRefine"
                    text: "Refine existing transparency"
                    checked: root.dataView.refine
                    toolTipText: "Process transparent images with the selected mode. Existing alpha can only decrease; hidden pixels stay hidden."
                    onToggled: backgroundRemoveService.configure("refine", checked)
                }
                KfpsCheckBox {
                    text: "Remove small islands"
                    checked: root.dataView.cleanup
                    enabled: !root.dataView.preserveOnly && root.dataView.mode !== "color"
                    toolTipText: "Remove tiny confident components and their soft edges. Optional; can remove small accessories. Disabled for logos."
                    onToggled: backgroundRemoveService.configure("cleanup", checked)
                }
                KfpsCheckBox {
                    text: "Include enclosed background"
                    visible: root.dataView.mode === "color"
                    checked: root.dataView.enclosed
                    toolTipText: "Remove the selected colour inside enclosed holes too. Disable to remove only background connected to an image edge."
                    onToggled: backgroundRemoveService.configure("enclosed", checked)
                }
                KfpsCheckBox {
                    text: "Remove colour fringe"
                    visible: root.dataView.mode === "color"
                    checked: root.dataView.decontaminate
                    toolTipText: "Unmix the selected background colour from antialiased edge pixels. Interior colours stay unchanged."
                    onToggled: backgroundRemoveService.configure("decontaminate", checked)
                }
                RowLayout {
                    Text { text: "CPU threads"; color: Theme.muted; font.family: Theme.fontFamily; font.pixelSize: Theme.px(12) }
                    KfpsComboBox {
                        objectName: "BackgroundRemoverThreads"
                        Layout.preferredWidth: Theme.px(100)
                        model: ["1", "2", "4", "8"]
                        currentIndex: [1, 2, 4, 8].indexOf(root.dataView.threads)
                        toolTipText: "Four threads recommended. Fewer threads leave more CPU time for other work."
                        onActivated: backgroundRemoveService.configure("threads", [1, 2, 4, 8][currentIndex])
                    }
                }
                GhostButton {
                    text: "Reset settings"
                    toolTipText: "Restore the recommended soft-edge anime settings. Existing corrections are not changed."
                    onClicked: backgroundRemoveService.configure("reset", true)
                }
                GhostButton {
                    text: "Reset corrections"
                    enabled: root.dataView.editable && root.dataView.canUndo
                    toolTipText: "Return to the initial cutout. This action can be undone."
                    onClicked: backgroundRemoveService.resetCorrections()
                }
            }
            GhostButton {
                objectName: "BackgroundRemoverReport"
                visible: root.dataView.report.length > 0
                text: "Run report"
                toolTipText: "Open the settings, result, timings and CPU worker log for this run."
                onClicked: backgroundRemoveService.openReport()
            }
        }
    }
}
