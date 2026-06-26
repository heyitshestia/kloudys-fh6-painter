from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from .models import DictListModel


TOPICS = [
    ("start", "Start here", "The safe seven-step workflow", [
        ("Prepare the source", "Use a clean, correctly cropped image. Transparent PNG is best for cutout designs."),
        ("Run Source Image Check", "Open Images first. Green is a practical source, yellow deserves a quick review, and red should be fixed before a long run."),
        ("Generate", "Choose a preset and template layer target. Leave advanced overrides off unless you know why you need them."),
        ("Review final checkpoints", "Generation is not finished when the GPU process stops. Wait for finalization, then compare the final previews."),
        ("Clean up in the editor", "Open a generated JSON in the Fabric editor for text, eyes, hard edges, masks, alignment, and deliberate hand work."),
        ("Prepare the game template", "Load the correct saved and reopened template, stay in the vinyl group editor, and enter its exact layer count."),
        ("Import, save, and reload", "Import once into a fresh template. Save and reopen the group before judging the result; the first live preview can be misleading."),
    ]),
    ("generate", "Generate vinyls", "What every generation control actually does", [
        ("Preset", "Shaded Character Art is the safest general choice. Flat Colors is for logos and broad hard regions. Smooth Gradients protects soft transitions."),
        ("Layer target", "This is both the generation budget and the game template size you intend to use. It must never exceed 3000."),
        ("Finalize checkpoints", "Comma-separated layer counts become your final visual choices. The target layer count is always retained."),
        ("2x Mode", "Doubles search samples. It can improve a close result, but takes longer and does not double the layer count."),
        ("Edge Repair", "A finalization pass for holes, cutout edges, fingers, hair gaps, and spill. Keep it off unless the source needs it."),
        ("Graceful Stop", "Requests a stop at the next safe saved point, then finalizes what exists. Force Stop is only for a stuck process."),
    ]),
    ("images", "Source images", "Avoid wasting a long generation on a bad input", [
        ("Resolution", "Very small art loses detail. Extremely large art costs time without guaranteeing a better vinyl. The source check explains the practical range."),
        ("Transparency", "A background that merely looks blank still consumes shapes. Check the alpha report and use background removal when needed."),
        ("Compression", "Avoid heavily compressed screenshots and tiny social-media copies. Clean PNG or good-quality JPEG/WebP gives the generator clearer boundaries."),
        ("Heatmap", "The heatmap highlights likely detail-critical edges. It is a diagnostic view, not a separate AI model or generator."),
    ]),
    ("json", "JSON browser", "Select the exact file that will be imported", [
        ("Sources", "Generated Finals are completed generator outputs. Editor Exports are saved by the Fabric editor. Exported Game JSONs come from game export or manual files."),
        ("Three-column browser", "Choose a generation/folder, then a checkpoint, then verify its preview, layer count, and full path in the inspector."),
        ("Selection safety", "The selected row stays selected when clicked again. Click empty browser space to clear it. Never import if the selected path is not the file you expect."),
        ("Long paths", "Paths are elided visually but retained in full. Hover for the tooltip or use Open Source Folder."),
    ]),
    ("transfer", "Import and export", "Moving vinyls between KFPS and supported games", [
        ("Game choice", "FH6, FH5, and FM8 are separate profiles. FM8 export remains experimental and converts supported resources toward the shared JSON structure."),
        ("Import prerequisites", "Open the game, enter the vinyl group editor, load a fresh saved/reopened circle template, ungroup when instructed, and enter the exact template count."),
        ("One import per fresh template", "Importing repeatedly into a used template can leave stale shape data. Reload a clean template for another attempt."),
        ("Export safety", "Export only your own editable group. Enter the visible layer count exactly. Grouped or nested vinyls can be harder to validate safely."),
    ]),
    ("editor", "Fabric editor", "Manual cleanup without touching the editor implementation", [
        ("What it is", "The editor remains the existing local browser application. KFPS starts its local server and opens it externally."),
        ("Projects", "Project files preserve internal editor state and overlays. They are not the same thing as import-ready JSON exports."),
        ("When to use it", "Use it for precise text, logos, alignment, masks, source tracing, color correction, layer ordering, and cleanup that automatic generation cannot infer."),
    ]),
    ("reports", "Reports and privacy", "Create useful local diagnostics", [
        ("Describe the failure", "Write what you clicked, what you expected, what actually happened, and the last successful step."),
        ("Context is optional", "App version and theme are safe defaults. Runtime logs and local file paths remain opt-in because they may contain private names or folders."),
        ("Nothing uploads automatically", "Preview and Save create Markdown locally. You decide whether and where to share it."),
    ]),
    ("updates", "Updates and runtime", "Keep the bundled application healthy", [
        ("Bundled Python", "KFPS requires 64-bit Python 3.12. A normal release includes it; users should not need to install a separate Python."),
        ("Dependency check", "Settings verifies the packaged backend modules. Missing modules usually mean the release was incomplete or extracted incorrectly."),
        ("Update handoff", "KFPS closes before running the updater so Windows can replace the executable safely. Generated and runtime data are preserved by the existing updater."),
    ]),
    ("troubleshooting", "Troubleshooting", "Start with the last meaningful log line", [
        ("Generation failed", "Read the line before the exit code. OpenCL or GPU messages point to driver/resource trouble; JSON errors happen later in the pipeline."),
        ("Game group not found", "Confirm the correct game is running, you are inside the right editor screen, and the layer count is exact. Try a fresh reopened template."),
        ("Wrong JSON", "Check the inspector path. Refresh the source and select the intended file again before importing."),
        ("Editor did not open", "Run Settings checks, then confirm the Fabric editor folder and launcher script exist. Browser security software can also block localhost pages."),
        ("App looks slow", "Disable glass effects or ambient motion in Settings. Runtime logs are batched so fast generator output does not redraw the interface for every line."),
    ]),
]


class HelpService(QObject):
    changed=Signal()
    def __init__(self,parent=None):
        super().__init__(parent);self._topic_model=DictListModel(["key","title","summary"]);self._filtered=list(TOPICS);self._index=0;self._replace()

    @Property(QObject, constant=True)
    def topicModel(self):return self._topic_model

    def _replace(self):self._topic_model.replace([{"key":k,"title":t,"summary":s} for k,t,s,_ in self._filtered])
    @Property(str,notify=changed)
    def title(self):return self._filtered[self._index][1] if self._filtered else "No topics"
    @Property(str,notify=changed)
    def summary(self):return self._filtered[self._index][2] if self._filtered else "Try another search."
    @Property("QVariantList",notify=changed)
    def sections(self):return [{"heading":h,"body":b} for h,b in self._filtered[self._index][3]] if self._filtered else []
    @Slot(str)
    def search(self,text):
        q=text.strip().lower();self._filtered=[topic for topic in TOPICS if not q or q in " ".join([topic[0],topic[1],topic[2],*(x for section in topic[3] for x in section)]).lower()];self._index=0;self._replace();self.changed.emit()
    @Slot(int)
    def select(self,index):
        if 0<=index<len(self._filtered):self._index=index;self.changed.emit()
