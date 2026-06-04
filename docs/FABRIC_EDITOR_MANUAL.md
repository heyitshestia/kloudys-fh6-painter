# KFPS Vinyl Editor Manual

This document covers the Fabric-based editor used by KFPS. It explains what the editor does, how each tool works, how JSON import/export is handled, and which editor-only features are intentionally removed before game import.

## Purpose

The editor is a browser-based vinyl editor for FH6-compatible JSON files. It is built around Fabric.js because SVG/canvas editing gives better manual control than editing raw JSON directly.

The editor is not the memory importer. It creates, loads, edits, and exports JSON files. The exported JSON still needs to be imported into FH6 by the app's import tools.

## Core Workflow

1. Open the editor from the app.
2. Import a JSON file or place shapes manually from the shape library.
3. Optionally add a source overlay image for tracing.
4. Move, scale, skew, rotate, recolor, group, hide, or lock editor layers.
5. Use guides and snapping for precise alignment.
6. Export one FH6-compatible JSON.
7. Import the exported JSON with the app's `Import JSON` tab.

## Supported Inputs

The editor accepts these practical input types:

- FH6 type-code JSON: full shape-library JSON with FH6 shape codes.
- FH6 generated JSON: rectangle/ellipse generator output.
- FH5 legacy generated JSON: older rectangle/ellipse JSON is converted into FH6 editor coordinates.
- Fabric editor project JSON: editor project saves with editor metadata such as groups, locks, hidden layers, and guides.

The editor rejects files that do not contain usable vinyl layer data. Failed imports leave the current canvas unchanged.

## Coordinate Model

The editor canvas is intentionally matched to the FH6 vinyl coordinate feel:

- Canvas origin is centered.
- X increases to the right.
- Y visually behaves like FH6 after conversion, not like raw browser pixel space.
- Shapes are converted into Fabric objects for editing and converted back into JSON on export.

Generated/legacy JSON and handmade FH6 JSON do not store every value in the same way. The editor normalizes them while loading, then restores the correct export format depending on which export button is used.

## Shape Library

The shape library is shown in the right-side panel.

Features:

- Shapes are grouped by the in-game families where possible.
- Shape names and FH6 words are loaded from `shape-names.json` and `shape-words.json`.
- Clicking a shape places it in the current viewport, not at a fixed world center.
- Newly placed shapes use the remembered active color.
- Favorite shapes can be toggled from the tile corner.
- Favorite shapes persist in browser local storage.
- Shape search matches family, name, index, and type code.
- Gradient Shapes render with their bundled fade masks in the editor preview while still exporting as normal FH6 gradient resources.
- Placement modes control what a clicked tile does:
  - Add at top: creates a new top layer.
  - Insert above selected: creates a new layer directly above the selected layer.
  - Insert below selected: creates a new layer directly below the selected layer.
  - Replace selected shape: keeps position, color, alpha, group, lock, and layer order, but swaps the selected layer's FH6 shape type.
- Reuse last font size can keep newly placed font shapes consistent after one font character has been resized.

Important: shape display thumbnails are editor UI only. Export uses the actual FH6 type code and geometry data.

## Selection Tools

### Tool Options Bar

The bar above the canvas keeps common actions visible instead of hiding everything in dock tabs.

It shows:

- Current tool.
- Selection count.
- Visible-only selection toggle.
- Invert box-select toggle.
- Shape click placement mode.
- Active color swatch.
- Quick duplicate, delete, group, and fit actions.
- Export readiness.

This follows the same general idea as Krita/Photoshop tool options: the detailed panels stay docked, but actions users need constantly remain reachable.

### Select / Move

The normal pointer mode is for selecting and moving layers.

Controls:

- Click a shape to select it.
- Drag a selected shape to move it.
- Drag the Fabric handles to scale, rotate, or skew.
- Drag empty canvas to box-select.
- Hold V while dragging to force box-select even if the drag starts on top of a shape.
- Hold Shift for multi-select behavior where Fabric supports it.
- Mouse wheel zooms.
- Middle/right mouse drag pans.

Duplicate follows the current placement mode. In `Add at top` mode, duplicated layers go to the top as usual. In `Insert above selected` or `Insert below selected`, duplicated layers keep their internal layer order and are inserted directly above or below the selected layer or selected range.

Selected shapes get an editor-only halo and stronger transform frame. This makes selected shapes readable when several neighboring layers use the same color. The halo/frame is not exported and does not change JSON.

### Invert Box Select

Invert box-select changes drag-box selection into "select everything outside this box".

Use it when a design has many layers and you want to isolate or delete everything except a specific region.

Rules:

- It only affects multi-layer box selections.
- Normal single clicks are unaffected.
- Hidden layers are skipped.
- Shift/Ctrl modified selections are not inverted.

### Box Select Visible Only

This option limits box selection to visible layers. Hidden editor layers are skipped.

Use it when a design has hidden construction layers or grouped sections that should not be accidentally selected.

## Transform Controls

Shapes can be moved, scaled, rotated, and skewed using Fabric's object controls.

The editor preserves the FH6 export math by converting Fabric transform values back into FH6-style data on export.

### Scaling

Scaling changes the visible size of the selected object. Negative scale signs are preserved where needed so imported legacy/generated JSON can round-trip correctly.

### Rotation

Rotation uses degrees. The editor normalizes angles when exporting.

### Skew

Skew/disform changes the shape slant. This is useful for matching perspective or angled surfaces.

Skew is more sensitive than move/scale. The guide snapping code is intentionally conservative during skew so it does not fight Fabric's active transform math.

Corner handles skew by default. Hold Shift while dragging a corner to use uniform/global scale instead of skew. Ctrl remains reserved for snapping, so Shift avoids conflicting with guide/grid behavior.

## Guides And Snapping

The Guides tool lets users draw editor-only guide lines. These lines help align shapes but are never exported.

Guide types:

- Free angled guides.
- Horizontal guides.
- Vertical guides.
- Optional grid lines.

Theme visibility:

- The pink theme uses darker grid, guide, and notch-ring colors so they remain visible on the pastel canvas.
- The dark theme uses white guide and notch-ring colors so snapping helpers stay readable.
- Draft guide lines use the same theme-aware guide color family and are not yellow.

Guide drawing:

- Select the Guides tool.
- Left-drag on the canvas to create a guide.
- Right-drag or middle-drag pans the canvas without leaving guide placement mode.
- Shift can constrain a free guide to horizontal or vertical while drawing.
- Guide endpoints can optionally snap to grid.
- Guides are saved in Fabric project files and autosave.

Guide deletion:

- Select the Guides tool.
- Click a guide.
- Press Delete or use Delete Selected Guide.

### Ctrl Snapping

By default, snapping only happens while Ctrl is held.

This prevents normal editing from jumping unexpectedly.

Behavior:

- Moving with Ctrl near a horizontal/vertical guide snaps position.
- Moving with Ctrl near an angled guide snaps the active dragged edge and can rotate the object to match the guide.
- Ctrl movement only considers angled guide snapping when the cursor is close to that guide line. This prevents dense grids or distant guides from making shapes jump unpredictably.
- Grid snapping checks the shape's left, right, top, and bottom sides so any side can lock onto a grid line.
- Scaling keeps the opposite edge anchored so only the pulled side changes size.
- Scaling with Ctrl can lock the pulled side onto a nearby guide line while keeping the opposite side planted.
- Skewing keeps the opposite edge anchored so the pulled side deforms without the whole shape walking across the canvas.
- Without Ctrl, the editor shows alignment helpers but does not move the object.

### Active-Edge Snapping

The editor does not blindly snap the shape center when an active side is known.

Examples:

- Pulling the right handle snaps the right edge.
- Pulling the left handle snaps the left edge.
- Pulling the top handle snaps the top edge.
- Pulling the bottom handle snaps the bottom edge.
- Dragging a shape infers the active side from the pointer position.
- The active side is frozen at the start of a drag. It does not keep changing mid-drag as the shape moves or rotates.

This makes it possible to fit a shape between two guide lines without the opposite side snapping by mistake.

### Angled Guides

Angled guides work differently depending on the transform:

- Move: active edge can snap and the object may rotate to match the guide.
- Scale: the opposite side is anchored; with Ctrl, the pulled side can resize until it locks onto a nearby guide line.
- Skew: the opposite side is anchored; the editor shows alignment helpers but does not translate or rotate the whole shape during the active transform.

This avoids the unstable "shape goes crazy" behavior caused by changing rotation or translating the object while Fabric is already scaling/skewing the same object.

Horizontal and vertical guide lines can also straighten a moved shape:

- Moving a top/bottom edge to a horizontal guide can rotate the shape back to horizontal.
- Moving a left/right edge to a vertical guide can rotate the shape back upright.
- This lets a shape recover from an angled-guide rotation without manually typing `0` degrees.

### Anchored Resize And Skew

When a shape is resized or skewed, the editor uses the side being pulled to infer the opposite anchor:

- Pull right: left side stays planted.
- Pull left: right side stays planted.
- Pull top: bottom side stays planted.
- Pull bottom: top side stays planted.
- Pull a corner: the opposite corner stays planted.

This matters most for skewed shapes. Without anchoring, a resize can make the entire shape drift away from the intended placement. With anchoring, shortening or elongating a skewed shape changes the pulled side while preserving the opposite side's position.

When Ctrl is held during scale, the editor tries to lock the pulled side to the closest guide that the anchored resize axis can reach. This is not a whole-object move. It changes the shape size around the fixed opposite edge.

## Rotation Notches

Rotation has an editor-only notched ring.

While rotating a shape:

- A temporary ring appears around the selected shape.
- Tick marks appear every 45 degrees.
- Major ticks appear at 0, 90, 180, and 270 degrees.
- The ring gets darker and more visible as the canvas is zoomed in.
- If the cursor is close to the ring and the current angle is close to a 45-degree notch, the editor gently snaps to that notch.
- If the cursor is away from the ring, the editor shows the ring but does not snap rotation.
- If the angle is not close, the editor leaves it alone.

This behaves like rotation snapping in Blender and other 3D/vector tools: it gives useful stops without forcing every rotation to a fixed angle.

The rotation ring is only a visual helper. It is not exported and does not count as a layer.

### Snap Overlay

While moving/scaling/skewing, the editor draws a temporary overlay:

- A cross splits the object into four visual regions.
- The active edge/contact point is highlighted.
- A projection indicator shows where the snap lands.

This overlay is editor-only. It is not saved into normal exports and does not count as a vinyl layer.

## Source Overlay

The overlay image is a tracing/reference image.

Features:

- Add an image as a source overlay.
- Adjust overlay opacity.
- Adjust overlay scale.
- Toggle overlay visibility.
- Remove overlay.
- Overlay moves with the canvas view.

The source overlay is never exported and never becomes a vinyl layer.

## Color Tools

### Active Color

The editor remembers the last active color. New shapes use this color by default.

When one layer is selected, color edits apply to that layer. When multiple layers are selected, color edits apply to every selected unlocked layer and locked layers are skipped.

### Color Picker

Click the color square to open the color picker.

Saved color slots:

- Sixteen saved color slots are available.
- Pick a slot, choose a color, and save it.
- Clicking a saved color applies it to the current selection. With multiple selected layers, it performs a batch recolor.
- Saved colors persist in browser local storage.

### Eyedropper

The eyedropper can pick from:

- Existing vinyl shapes.
- The source overlay image when no shape is clicked.

The eyedropper does not change selection while picking. This makes it safe to sample a color and apply it to the already selected layer.

### Live Overlay Color

When enabled, the selected shape can sample the dominant/representative color under its current footprint from the source overlay.

This is useful for tracing over an image:

- Place a shape.
- Resize it over the desired area.
- Let the editor sample the source image color.

If there is no overlay pixel under the shape, the color stays unchanged.

## Layer Panel

The layer panel shows editable vinyl layers.

Features:

- Select layers from the list.
- Search/filter layers.
- Hide/show layers.
- Lock/unlock layers.
- Move layers forward/backward.
- Duplicate layers.
- Delete layers.

Layer order matters because FH6 draws higher layers over lower layers.

## Editor Groups

Editor groups are internal organization only.

What groups do:

- Let several layers collapse under one group in the layer list.
- Let users hide or lock a whole group.
- Keep complex designs manageable.

What groups do not do:

- They do not export as FH6 groups.
- They do not change JSON layer order.
- They do not affect game import beyond the flat layer list.

This is intentional because the importers expect flat layer lists.

## Locks And Hidden Layers

Locked layers cannot be edited by normal editor actions.

Hidden layers are not visible in the editor.

Project saves preserve locks and hidden state. Normal exported vinyl JSON can include hidden/locked editor metadata only when saving as a Fabric project; game/import exports stay focused on vinyl layer data.

## Undo And Redo

Undo/redo tracks editor layer changes.

The editor protects the loaded source point so Ctrl+Z cannot go back far enough to remove the loaded source and leave a blank canvas unintentionally.

Autosave updates after successful history changes when browser storage allows it.

## Autosave

Autosave stores:

- Loaded project name.
- Current shapes.
- Editor guides.
- Editor metadata where applicable.

Autosave is kept in browser local storage. If storage is full or unavailable, the editor continues working and reports that autosave was skipped.

## Export Buttons

The editor has one game/import export path.

### Export FH6 JSON

Use this for all editor exports.

This export keeps FH6 type-code shape information and should be used for:

- Hand-edited shape-library designs.
- Designs made inside this editor using non-generated shapes.
- Full community shape/font shape designs.
- Generated designs after manual cleanup.

Import this with the app's `Import JSON` tab.

## Why There Is One Importer

Generated finals, editor exports, game exports, and hand-edited shape-code JSONs now go through the same app import path.

The importer accepts:

- legacy generated rectangle/ellipse JSON
- current FH6 type-code JSON
- editor exports
- game exports from normal editable user-owned groups

The editor therefore exports only one JSON type: FH6-compatible type-code JSON for the unified importer.

## JSON Conversion Notes

The editor uses conversion in both directions:

- JSON to Fabric object for editing.
- Fabric object back to JSON for import.

Generated/FH5 legacy data needs special conversion for:

- Position.
- Y-axis direction.
- Rotation direction.
- Rectangle vs ellipse divisors.
- Scale signs.
- Skew.

FH6 handmade data keeps:

- Full shape type code.
- Type word.
- Resource family/index when known.
- Color.
- Alpha.
- Mask flag when present.
- Extra data fields where needed.

## What Is Editor-Only

These do not export as vinyl layers:

- Source overlay image.
- Guide lines.
- Grid lines.
- Snap overlay.
- Selection outlines.
- UI panels.
- Internal editor groups for organization.

## Known Practical Rules

- Use Export FH6 JSON for generated, handmade, or editor-created layers.
- If a shape behaves strangely during skew, release the handle and try a smaller adjustment.
- Use Ctrl snapping for precise placement, not for every drag.
- Keep source overlay opacity low enough to see white shapes.
- Save Fabric project files if you want to preserve editor-only guides/groups/locks.
- Press Enter inside transform fields to apply typed values without clicking the apply button.
- If two same-color shapes are hard to tell apart, select one layer from the canvas or layer list. The editor-only halo marks the selected layer without changing export data.

## Current Stability Tests

The editor was tested with local Playwright coverage for:

- Page load and non-blank UI.
- Shape library availability.
- Guide/grid creation.
- Center fallback snapping.
- Active-edge diagonal guide snapping.
- Ctrl move with active edge rotation.
- Horizontal/vertical guide straightening after angled rotation.
- Ctrl scale with opposite edge anchoring and no mid-transform rotation.
- Ctrl scale active-side guide locking with opposite edge anchoring.
- Ctrl skew with opposite edge anchoring and no mid-transform rotation.
- Rotation 45-degree notch snapping and ring cleanup.
- No-Ctrl visual overlay without snapping.
- Locked layer safety.
- Guide mode disengaging when layer editing starts.
- Export snapshot not leaking guides or snap overlays.
- FH5 handmade compatibility input.
- FH6 handmade compatibility input.
- Generated JSON compatibility input.
- Failed import safety.
- Autosave quota behavior.
- Corrupt local storage startup.
- Multiselect nudge behavior.
- Hidden/locked/editor group project round-trip.

## Relevant Files

- `tools/fabric-editor/index.html`: editor markup and panels.
- `tools/fabric-editor/style.css`: editor layout, themes, panels, and controls.
- `tools/fabric-editor/editor.js`: editor behavior, conversion math, snapping, import/export, layer tools.
- `tools/fabric-editor/shape-names.json`: display names.
- `tools/fabric-editor/shape-words.json`: FH6 shape words.
- `tools/fabric-editor/Resources/Vinyls`: bundled shape geometry/thumbnails.

## Development Notes

Snapping is intentionally split into visual and active behavior:

- The visual overlay appears during transform operations so the user can see alignment intent.
- Actual snapping only happens when Ctrl is held unless the snap settings are changed.
- Active-edge angled guide snapping has priority over grid snapping once an active side/corner is known.
- Rotation is allowed during move snapping but disabled during scale/skew transforms to avoid Fabric transform instability.
- Scale/skew transforms use a mouse-down snapshot to keep the opposite edge anchored while the pulled edge changes.
- Ctrl scale can calculate the intersection between the pulled edge's resize axis and a guide line, then adjust scale instead of translating the object.
- Rotation notches use editor-only overlay objects tagged the same way as snap helpers, so they are automatically excluded from exports.

This separation is the main safeguard against the Ctrl+skew/resize instability.
