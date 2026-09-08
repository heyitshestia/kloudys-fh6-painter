import QtQuick 6.7
import QtQuick.Controls 6.7
import Kfps.Theme 1.0

Rectangle {
    id: root
    property string sourceUrl: ""
    property string outputUrl: ""
    property string maskUrl: ""
    property real imageWidth: 1
    property real imageHeight: 1
    property bool busy: false
    property bool editable: false
    property string tool: "pan"
    property int viewMode: 0
    property real comparePosition: 0.5
    property real brushSize: 60
    property real zoom: 1
    property real panX: 0
    property real panY: 0
    property var stroke: []
    property bool drawing: false
    readonly property real fitScale: Math.max(0.0001, Math.min((width-24)/Math.max(1,imageWidth), (height-24)/Math.max(1,imageHeight)))
    readonly property real imageScale: fitScale*zoom
    readonly property real imageX: (width-imageWidth*imageScale)/2+panX
    readonly property real imageY: (height-imageHeight*imageScale)/2+panY
    readonly property real imageW: imageWidth*imageScale
    readonly property real imageH: imageHeight*imageScale
    signal corrected(string tool, var points, real diameter)
    signal sampled(real x, real y)
    signal dropped(string url)
    color: Theme.surface
    border.color: Theme.border
    clip: true
    onSourceUrlChanged: { clearStroke(); fit() }
    onToolChanged: { clearStroke(); if (tool !== "pan" && tool !== "pick") viewMode=1 }
    onBusyChanged: { if (busy) clearStroke() }
    function clearStroke() { stroke=[]; drawing=false; ink.requestPaint() }
    function finishStroke() {
        const points=stroke, active=drawing;
        clearStroke();
        if (!active || !points.length) return;
        if (tool === "pick") sampled(points[0][0],points[0][1]);
        else corrected(tool,points,brushSize);
    }
    function fit() { if (drawing) return; zoom=1; panX=0; panY=0 }
    function zoomBy(factor, x, y) {
        if (drawing) return;
        const next=Math.max(1,Math.min(12,zoom*factor));
        const ratio=next/zoom;
        panX=(panX+width/2-x)*ratio-(width/2-x);
        panY=(panY+height/2-y)*ratio-(height/2-y);
        zoom=next;
        if (zoom === 1) { panX=0; panY=0 }
    }
    function point(x,y) {
        const px=(x-imageX)/imageW, py=(y-imageY)/imageH;
        return px>=0 && px<=1 && py>=0 && py<=1 ? [px,py] : null;
    }
    ArtworkPreviewBackdrop { anchors.fill: parent }
    Image {
        x: root.imageX; y: root.imageY; width: root.imageW; height: root.imageH
        source: root.tool === "pick" || root.viewMode === 2 ? root.sourceUrl
                : root.viewMode === 3 && root.maskUrl ? root.maskUrl : (root.outputUrl || root.sourceUrl)
        asynchronous: true; cache: false; smooth: true
    }
    Item {
        visible: root.viewMode === 0 && root.tool !== "pick" && root.outputUrl.length > 0
        width: parent.width*root.comparePosition; height: parent.height; clip: true
        ArtworkPreviewBackdrop { width: root.width; height: root.height }
        Image {
            x: root.imageX; y: root.imageY; width: root.imageW; height: root.imageH
            source: root.sourceUrl; asynchronous: true; cache: false; smooth: true
        }
    }
    Rectangle {
        visible: root.viewMode === 0 && root.tool !== "pick" && root.outputUrl.length > 0
        x: root.width*root.comparePosition; width: 2; height: root.height; color: Theme.primaryBright
    }
    Canvas {
        id: ink
        anchors.fill: parent
        onPaint: {
            const ctx=getContext("2d"); ctx.clearRect(0,0,width,height);
            if (!root.stroke.length || !root.drawing || (root.tool !== "erase" && root.tool !== "restore")) return;
            ctx.strokeStyle=root.tool === "restore" ? "#49c792" : "#fa619d";
            ctx.fillStyle=ctx.strokeStyle; ctx.globalAlpha=0.65;
            ctx.lineWidth=Math.max(1,root.brushSize*root.imageScale); ctx.lineCap="round"; ctx.lineJoin="round";
            ctx.beginPath();
            for (let i=0;i<root.stroke.length;i++) {
                const p=root.stroke[i], x=root.imageX+p[0]*root.imageW, y=root.imageY+p[1]*root.imageH;
                if (!i) ctx.moveTo(x,y); else ctx.lineTo(x,y);
            }
            ctx.stroke();
            const p=root.stroke[0]; ctx.beginPath();
            ctx.arc(root.imageX+p[0]*root.imageW,root.imageY+p[1]*root.imageH,ctx.lineWidth/2,0,2*Math.PI); ctx.fill();
        }
    }
    MouseArea {
        id: mouse
        objectName: "BackgroundRemoverPaintArea"
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.MiddleButton
        hoverEnabled: true
        enabled: !root.busy && root.sourceUrl.length > 0
        preventStealing: true
        cursorShape: root.tool === "pan" ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.CrossCursor
        property bool panning: false
        property real lastX: 0
        property real lastY: 0
        onPressed: function(event) {
            panning=root.tool === "pan" || event.button === Qt.MiddleButton;
            lastX=event.x; lastY=event.y;
            if (panning) return;
            const p=root.point(event.x,event.y);
            if (!p || (root.tool !== "pick" && !root.editable)) return;
            root.stroke=[p]; root.drawing=true; ink.requestPaint();
        }
        onPositionChanged: function(event) {
            if (!pressed) return;
            if (panning) {
                root.panX+=event.x-lastX; root.panY+=event.y-lastY;
                root.panX=Math.max(-root.imageW/2,Math.min(root.imageW/2,root.panX));
                root.panY=Math.max(-root.imageH/2,Math.min(root.imageH/2,root.panY));
                lastX=event.x; lastY=event.y; return;
            }
            if (!root.drawing || (root.tool !== "erase" && root.tool !== "restore")) return;
            const p=root.point(event.x,event.y);
            if (!p) { root.finishStroke(); return }
            if (p && root.stroke.length<4096) {
                const previous=root.stroke[root.stroke.length-1];
                if (Math.hypot((p[0]-previous[0])*root.imageW,(p[1]-previous[1])*root.imageH)>=1) {
                    root.stroke=root.stroke.concat([p]); ink.requestPaint();
                }
            }
        }
        onReleased: function(event) {
            if (panning) { panning=false; root.clearStroke(); return }
            root.finishStroke();
        }
        onCanceled: { root.clearStroke(); panning=false }
        onWheel: function(wheel) { root.zoomBy(wheel.angleDelta.y>0 ? 1.2 : 1/1.2,wheel.x,wheel.y); wheel.accepted=true }
    }
    Rectangle {
        visible: mouse.containsMouse && !root.busy && root.editable && (root.tool === "erase" || root.tool === "restore")
        width: Math.max(2,root.brushSize*root.imageScale); height: width; radius: width/2
        x: mouse.mouseX-width/2; y: mouse.mouseY-height/2
        color: "transparent"; border.width: 1; border.color: "white"
    }
    DropArea {
        anchors.fill: parent; enabled: !root.busy
        onDropped: function(drop) {
            if (drop.hasUrls && drop.urls.length === 1) { root.dropped(drop.urls[0]); drop.acceptProposedAction() }
        }
    }
}
