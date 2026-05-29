# Kloudy's FH6 Painter Changelog

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
