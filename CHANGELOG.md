# Kloudy's FH6 Painter Changelog

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
