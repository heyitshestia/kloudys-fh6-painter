# Development Roadmap

These are the current high-value workflow improvements being worked off in order.

| Status | Item |
| --- | --- |
| Done | Rename the standalone executable to `Kloudys Painter Launcher.exe` and make the updater migrate the old name. |
| Done | Make updater safer and clearer: logs, backups, version before/after, and launcher-first update flow. |
| Done | Add a clear generation phase banner: internal build -> Finalize Checkpoints -> ready to import. |
| Done | Make the finalized JSON browser more informative with preview, layer count, error score, preset, and source image metadata. |
| Done | Add recommendation tags such as best score, safest for template, lowest layer count, and latest. |
| Done | Add side-by-side finalized checkpoint comparison. |
| Done | Show exact preset settings and use cases directly in the UI. |
| Removed | Add first-run guided checklist mode. |
| Done | Improve technical errors into user-actionable messages. |
| Done | Add crash-safe Finalize Checkpoints resume for unfinished runs. |
| Done | Add release packaging automation with zip verification and no generated-output leakage. |
| Next | Generator V6: port scanline scoring/rendering and native boundary/uncovered weight maps while keeping Kloudy's mixed-shape pipeline. |
| Done | Add source cleanup for bad background removers: remove or hard-threshold low-alpha fringe pixels before generation so transparent haze does not waste samples and layers. |
