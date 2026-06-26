pragma Singleton
import QtQuick 6.7

QtObject {
    // Continuous scale derived from the live window dimensions. Every visual
    // metric flows through effectiveScale instead of discrete window presets.
    property real viewportScale: 1.0
    property real uiScale: 1.0
    property bool reducedMotion: false
    property bool ambientMotion: true
    property bool glassEffects: true

    readonly property color backgroundA: "#07050d"
    readonly property color backgroundB: "#120915"
    readonly property color backgroundC: "#260e24"

    readonly property color surface: "#c6150e1d"
    readonly property color surfaceSoft: "#ad0d0913"
    readonly property color surfaceStrong: "#d91d1325"
    readonly property color surfaceRaised: "#ed25162d"
    readonly property color surfaceTop: "#b72d2036"
    readonly property color surfaceBottom: "#d0100a17"
    readonly property color surfaceStrongTop: "#cc37243d"
    readonly property color surfaceStrongBottom: "#dd160d20"

    readonly property color border: "#765e4b68"
    readonly property color borderSoft: "#4f49334f"
    readonly property color borderStrong: "#b78a667f"
    readonly property color divider: "#3d493445"
    readonly property color text: "#fff8fc"
    readonly property color muted: "#d8c9d5"
    readonly property color subtle: "#a98fa4"
    readonly property color faint: "#755f73"

    readonly property color primary: "#ea3c88"
    readonly property color primaryBright: "#ff78b6"
    readonly property color primaryHot: "#ff4c9a"
    readonly property color primaryDeep: "#9c174f"
    readonly property color primarySoft: "#4dea3c88"
    readonly property color hover: "#22ff8fc2"
    readonly property color success: "#60dc91"
    readonly property color warning: "#ffc66d"
    readonly property color danger: "#ff536f"
    readonly property color consoleBackground: "#ee09060e"
    readonly property color shadow: "#d5000000"
    readonly property color innerHighlight: "#2d8a5a7d"
    readonly property color focus: "#ffff9ac8"

    readonly property string fontFamily: Qt.platform.os === "windows" ? "Segoe UI Variable Text" : "Inter"
    readonly property string displayFamily: Qt.platform.os === "windows" ? "Segoe UI Variable Display" : "Inter"
    readonly property string monoFamily: Qt.platform.os === "windows" ? "Cascadia Mono" : "monospace"

    readonly property real effectiveScale: Math.max(0.72, viewportScale * uiScale)

    // Single continuous geometry scale used by every component and page.
    function px(value) {
        return Math.round(value * effectiveScale * 100) / 100
    }

    // Responsive fallbacks activate only when user zoom or an extreme aspect
    // ratio genuinely leaves less logical room.
    function logical(value) {
        return value / effectiveScale
    }

    function isAtLeast(renderedWidth, designWidth) {
        return logical(renderedWidth) >= designWidth
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value))
    }
}
