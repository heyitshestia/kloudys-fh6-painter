import QtQuick 6.7
import QtQuick.Controls 6.7
import QtQuick.Layouts 6.7
import Kfps.Theme 1.0
import "../components"

Popup {
    id: root
    objectName: "DcinsideKoreanWelcomeOverlay"
    parent: Overlay.overlay
    width: parent ? parent.width : 0
    height: parent ? parent.height : 0
    padding: 0
    margins: 0
    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose

    function dismiss() {
        settings.acknowledgeDcinsideKoreanNotice()
        close()
    }

    onOpened: acknowledge.forceActiveFocus()
    background: Item { }
    Overlay.modal: Item { }

    contentItem: Item {
        Accessible.role: Accessible.Dialog
        Accessible.name: "DCInside의 KFPS 유저 여러분께!"
        Keys.onEscapePressed: root.dismiss()

        Rectangle { anchors.fill: parent; color: "#bb000000" }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            onWheel: function(wheel) { wheel.accepted = true }
        }
        Rectangle {
            id: panel
            objectName: "DcinsideKoreanWelcomePanel"
            anchors.centerIn: parent
            width: Math.min(Theme.px(880), Math.max(0, root.width - Theme.px(40)))
            height: Math.min(body.implicitHeight + acknowledge.implicitHeight + Theme.px(72),
                             Math.max(0, root.height - Theme.px(40)))
            color: Qt.rgba(Theme.surfaceRaised.r, Theme.surfaceRaised.g, Theme.surfaceRaised.b, 1)
            radius: Theme.corner(Theme.px(8))
            border.width: Theme.px(1)
            border.color: Theme.borderStrong

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.px(26)
                spacing: Theme.px(20)
                FastScrollView {
                    id: messageScroll
                    objectName: "DcinsideKoreanWelcomeScroll"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: availableWidth
                    contentHeight: body.implicitHeight
                    rightPadding: Theme.px(24)
                    ScrollBar.vertical: KfpsScrollBar {
                        objectName: "DcinsideKoreanWelcomeScrollBar"
                        parent: messageScroll
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        policy: ScrollBar.AsNeeded
                        visible: messageScroll.contentHeight > messageScroll.availableHeight
                    }
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    clip: true

                    Column {
                        id: body
                        objectName: "DcinsideKoreanWelcomeBody"
                        width: messageScroll.availableWidth
                        spacing: Theme.px(12)

                        Repeater {
                            model: [
                                "DCInside의 KFPS 유저 여러분께! 😊",
                                "DCInside에서 KFPS에 대해 이야기해 주시는 글들, 저도 다 보고 있어요! ㅋㅋ",
                                "사실 이 글은 제가 <b>DCInside 유저분들께 어떻게든 직접 닿아보려고 하는 시도</b>예요.<br>IP 제한 때문에 계정 만드는 것부터 거의 불가능한 데다가, 번역기를 거쳐서 글 하나하나 확인하는 것도 꽤 번거롭고 번역이 정확하지 않을 때가 많아서요 ㅠㅠ<br>그래도 여러분이 올려주시는 피드백은 놓치고 싶지 않아요!",
                                "혹시 KFPS를 사용하면서 겪고 있는 버그나 문제점들을 <b>한 게시글에 모아서</b> 정리해 주실 수 있을까요? 제가 확인하고 하나씩 고칠 수 있게요!",
                                "그리고 지금 올라오는 제보들 중에는 <b>KFPS 버전이나 하드웨어 정보가 빠져 있는 경우가 많아서</b>, 원인을 찾기가 어려운 경우가 있어요.",
                                "서양 유저들과 비교하면 여기 계신 분들은 KFPS를, 특히 <b>에디터를 정말 제대로 스트레스 테스트하고 계신 것 같아요 ㅋㅋ</b><br>여기서 언급되는 문제들 중에는 <b>제가 지금까지 한 번도 들어보지 못한 것들도 정말 많아서</b>, 꼭 찾아내서 고치고 싶어요!",
                                "그래서 가능하면 KFPS에 있는 <b>&quot;Report a Problem&quot; 기능도 꼭 사용해 주세요!</b><br>버튼을 누르면 신고 내용을 확인하고 Discord로 로그인해 전송할 수 있어요. 문제 내용은 공개 지원 게시판에 올라가요. 추가 기술 정보는 포함 여부를 직접 선택할 수 있고, <b>저와 권한이 있는 운영진만 볼 수 있어요.</b>",
                                "여러분의 제보가 정말 큰 도움이 됩니다. 정말 감사합니다!! 🙏",
                                "-Kloudy"
                            ]
                            delegate: Text {
                                required property int index
                                required property string modelData
                                objectName: "DcinsideKoreanParagraph" + index
                                width: body.width
                                text: modelData
                                textFormat: Text.StyledText
                                wrapMode: Text.Wrap
                                color: Theme.text
                                font.family: "Malgun Gothic"
                                font.pixelSize: Theme.px(index === 0 ? 20 : 16)
                                font.bold: index === 0
                                lineHeight: 1.3
                            }
                        }
                    }
                }
                PrimaryButton {
                    id: acknowledge
                    objectName: "DcinsideKoreanWelcomeGotIt"
                    Layout.alignment: Qt.AlignRight
                    text: "알겠어요!"
                    toolTipText: "이 안내를 닫고 다시 표시하지 않아요."
                    textPixelSize: Theme.px(15)
                    onClicked: root.dismiss()
                }
            }
        }
    }
}
