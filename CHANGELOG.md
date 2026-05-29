# Kloudy's FH6 Painter Changelog

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
