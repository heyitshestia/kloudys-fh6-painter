# Kloudy's FH6 Painter Changelog

## 2.0.33
- Restored the stable 2.0.27 editor baseline while keeping the current generator preset updates.
- Kept the updated raw FH6 import/export locator backend without experimental editor shape-resource caching.
- Removed the WIP seed/resource editor path from the shipped build.

## 2.0.27

- Changed Fabric editor corner dragging so normal corner drag scales shapes globally by default.
- Changed Fabric editor Shift+corner drag to skew shapes instead of scaling them.
- Reworked single-shape selection visuals so unselected shapes stay flat and selected shapes use an internal clipped rim instead of an outside halo.
- Reduced high-zoom manipulation UI clutter while keeping large invisible hit areas for easier grabbing.

## 2.0.26

- Added Ctrl-click layer-list multi-select in the Fabric editor so individual non-contiguous layers can be selected together.
- Fixed multi-selected layers moving unpredictably by normalizing Fabric selections before rebuilding them.
- Fixed drifting or stale editor hit boxes by syncing Fabric canvas geometry after layout changes, imports, shape creation, duplication, replacement, and transforms.
- Improved selected-shape highlighting so it uses a boundary-only outer edge outline without internal mesh geometry or flashing filled interiors.

## 2.0.25

- Improved Fabric editor selected-shape outlines so zoomed-in borders sit outside the vinyl shape instead of covering the shape edge.

## 2.0.24

- Fixed Fabric editor layer-list Shift-click range selection after scrolling or pointer-drag handling.
- Improved layer-list selection anchoring so contiguous ranges remain selected reliably.

## 2.0.23

- Improved Fabric editor responsiveness and selection behavior for dense vinyls.
- Added source-overlay move controls so reference images can be adjusted without grabbing vinyl layers.
- Improved guide handling so guide changes participate more reliably in undo/redo.

## 2.0.22

- Improved Fabric editor transform handles with more usable Figma-style corner, side, and rotate controls.
- Improved Fabric editor drag and pan performance by removing expensive selected-shape shadows and avoiding inactive snap overlay work.
- Added layered SVG overlay controls for flipping through reference, guide, and color layers.
- Removed internal development notes from the public package.

## 2.0.21

- Fixed shared JSON preview transforms for exported vinyls with negative scale and skew.
- Improved grouped export flattening so unresolved child groups are not exported as blank drawable shapes.

## 2.0.20

- Relaxed grouped vinyl export validation to reduce false refusals and improved parent negative-scale handling during grouped export flattening.

## 2.0.19

- Improved Fabric editor mask handling, layer editing, shortcuts, and small-shape transform controls.

## 2.0.18

- Improved diagnostic log privacy for import/export troubleshooting.

## 2.0.17

- Improved grouped and nested FH6 export flattening so parent group scale, rotation, skew, and negative scale are applied to child layers instead of only parent position.
- Improved fast export validation so current game exports can use the fast locator report without requiring the old fallback probe report.

## 2.0.16

- Added a basic FH5/FH6 target switch for import/export testing.
- Added a small FH5 compatibility notice in the importer and exporter.
- Improved shared JSON preview handling for generated, handmade, editor, and exported JSONs.
- Improved Fabric editor JSON browser and editor startup behavior.

## 2.0.10

- Fixed the native Windows launcher opening the launcher window behind other windows.
- Verified launcher setup buttons still run the Python setup and dependency setup batch files correctly.

## 2.0.9

- Rebuilt the Windows launcher as a smaller native launcher.
- Improved updater handling when the launcher executable is still running or locked.
- Added release checks to prevent packaging the old launcher format again.

## 2.0.8

- Fixed Fabric editor transform behavior for mirrored shapes, side resizing, corner skewing, and light-theme selection visibility.
- Improved editor JSON round-trip handling for negative scale values.

## 2.0.7

- Improved FH6 import/export memory locating from grouped, ungrouped, and nested-group dump analysis.
- Unified the app importer around one JSON import flow for generated finals, editor exports, hand-edited JSONs, and game exports.
- Made the Import JSON page fit the default app window without an outer page scroll; only the checkpoint list scrolls.
- Added a compact read-only FH6 research dumper for collecting locator diagnostics.

## 2.0.2

- Fixed Fabric editor live overlay color adoption for newly added, moved, nudged, and manually edited shapes.

## 2.0.1

- Fixed Fabric editor primitive import/export mapping so FH6 JSONs keep normal primitive shapes instead of resolving some codes to the wrong border-style resources.

## 2.0.0

- Reworked the main app shell into a wider workflow layout with a left-side navigation rail and dashboard.
- Added a local-only Bug Reports page that builds redaction-friendly reports for preview, copy, or local save without automatic upload.
- Added Eurocorp, Elite, CryNet, UNATCO, New Eden, Red Phosphorous, Blackout Violet, Blue Terminal 90s, and Matrix Green themes.
- Added BIOS-style Blue Terminal visuals, Matrix Green animated falling-code visuals, and terminal-safe monospace sizing.
- Added an optional Blue Terminal 90s dial-up sound loop while generation is running.
- Moved generator Pro Settings for manual resolution/random/mutated sample overrides into Settings while keeping layer count and finalize checkpoints in the Generate page.

## 1.10.80

- Corrected Fabric editor primitive names against the actual bundled primitive thumbnails instead of the old FH5-derived order.

## 1.10.79

- Restored verified primitive display names in the Fabric editor, so basic shapes such as Square and Circle are named normally again.

## 1.10.78

- Fixed Fabric editor full-library shape placement so chosen shapes keep their exact family/resource slot instead of reverse-mapping colliding FH6 words back to primitives.
- Fabric editor exports now preserve `resource_family`, `resource_index`, and `shape_name` metadata for reliable editor round-trips.

## 1.10.77

- Changed Fabric editor non-font shape labels to verified FH6 family/slot/word labels instead of guessed FH5-derived names.
- Font pages still show FH6 font glyph labels from the dumped font registry.

## 1.10.76

- Updated the Fabric editor color controls with an 8-slot saved-color picker, shape/source eyedropper toggle, and protected undo floor for loaded designs.
- Fixed Fabric editor shape-library slot mapping so FH6 shape words follow the calibrated slot order instead of one-by-one FH5-style increments.
- Filled missing FH6 font labels from the dumped font registry, including lower-case A slots.

## 1.10.75

- Fixed late-generation stalls where the generator kept retrying after the detail gate was mostly satisfied while the visible layer timer still looked fast.
- Generator logs now show accepted-layer wall time and retry count, making slow late layers visible instead of hidden.
- Presets now use bounded no-improvement retry counts and less aggressive late weak-shape gating.
- Added a permanent app-folder verification check to the bundled generator executable.

## 1.10.74

- Updated the V7 presets from prototype quality testing.
- Flat Colors now uses stronger edge-detail sampling with guarded rectangle use.
- Shaded Character Art now uses stricter late weak-shape gating and finer late-detail sampling.
- Smooth Gradients now uses a lower sample count with tuned soft-detail weighting for similar quality at better speed.

## 1.10.73

- Updated the GitHub updater to stop stale Kloudy's Painter generator/editor/app subprocesses automatically before syncing.
- The updater now logs which known process IDs it stopped and only fails if Windows refuses to terminate one.

## 1.10.72

- Replaced the Editor tab launcher with the bundled Fabric FH6 editor.
- Added the Fabric editor shape library with searchable shape names, explicit favorite buttons, remembered shape color, viewport-centered shape placement, and live overlay color sampling.
- Removed the editor canvas guide frame from the default view for cleaner manual placement.

## 1.10.68

- Promoted the tested prototype generator to `KloudysGeneratorV7.exe`.
- Updated the shipped presets for V7 raw-first output: sharper shaded-character defaults, lower rectangle pressure on faces/gradients, and legacy Edge Repair disabled by default.
- Updated the app, release packager, and updater cleanup rules to use V7 and retire old V6 generator binaries during updates.
- Added generator V7 notes so future tuning work stays documented instead of living only in test folders.

## 1.10.67

- Fixed FH6 imports reusing stale auto-locate session data after a previous import/save/reopen cycle.
- Normal FH6 imports now force a fresh template scan before every write.
- Added a final live group count/vector safety check inside the importer so stale tables abort before any layer is written.

## 1.10.66

- Hardened FH6 template locating by rejecting stale layer tables whose group vector metadata does not match the active editor template.
- Handmade import now requires a fresh saved/reopened plain white circle template before writing, preventing second-import writes into already-trimmed groups.
- Renamed the bundled V6 generator executable to `KloudysGeneratorV6.exe` and made the updater remove the old filename.
- Converted in-app `?` help buttons to hover tooltips.
- Added generator V6 follow-up notes for future tuning work.

## 1.10.65

- Added the bundled Forza Vinyl Studio editor as an `Editor` tab launcher.
- Shipped the editor as a self-contained Windows runtime so users do not need to install .NET separately.
- Added Forza Vinyl Studio credits and license notices.
- Replaced the old standalone Luma Band Pass tab with the editor launcher.
- Made the footer Ko-fi support button wider and marked it as optional.

## 1.10.64

- Updated the bundled generator to `KloudysGeneratorV6.exe`.
- Reworked the stock presets to `Shaded Character Art`, `Flat Colors`, and `Smooth Gradients`.
- Presets now keep their own resolution/sample settings by default; Pro settings are the only manual override.
- Added adaptive late-layer workload controls to the shipped preset files.

## 1.10.63

- Finalization now preserves the requested layer budget when covered-layer cleanup has no excess layers to remove.
- Flat opaque/luma runs now stabilize large single-color regions to reduce milky color variation in broad fields.

## 1.10.62

- Launcher version and changelog checks now prefer GitHub contents/raw API responses, with raw file URLs as fallback.
- This avoids stale raw-CDN version text immediately after pushes.

## 1.10.61

- Launcher GitHub checks now read from `refs/heads/main` so version and changelog checks avoid stale raw `main` aliases.

## 1.10.60

- GitHub version and changelog checks now use cache-busted raw URLs so the launcher sees fresh `main` updates more reliably.

## 1.10.59

- Launcher changelog now loads update notes from GitHub `main` instead of reading local updater log files.
- The launcher keeps the live action log small at the bottom while the larger upper pane shows these GitHub update notes.
- If GitHub cannot be reached, the launcher falls back to the bundled local `CHANGELOG.md`.

## 1.10.58

- Added a slim Ko-fi support button to the bottom footer of the main app.
- The Ko-fi button opens the support page in the default browser and stays outside all workflow tabs.
- Restored the shipped generator binary to the tracked main version after local engine testing.

## 1.10.57

- Improved transparent fringe cleanup before generation so bad background-removal pixels have less impact on edges and source matching.
- Kept the generator/output workflow compatible with existing presets and finalized JSON browsing.
