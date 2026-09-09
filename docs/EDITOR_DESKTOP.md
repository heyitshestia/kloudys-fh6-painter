# Independent Editor Window

This is a host and lifetime split, not a Fabric replacement or editor rewrite.
The same HTML, scripts, bundled shapes, and project/export APIs run inside a
PySide6 Qt WebEngine window in a separate process.

## Launch And Ownership

- `KFPS Editor.exe` starts `KFPS.UI/editor.py` without starting the main KFPS UI.
- The main Editor page starts or activates the same process through `EditorService`.
- A root-scoped, current-user local connection and a process lock prevent duplicate
  desktop owners. Additional launch requests are serialized; open dialogs and
  unsaved work are respected before another project replaces the canvas.
- The editor owns the loopback server, browser profile, and recovery writes.
  Closing KFPS disconnects its project-list client, not the editor.
- The server tries its previous local port and chooses another when occupied.
  Preferences and recovery do not depend on that port remaining available.
- Server and desktop markers are removed on orderly shutdown. Stale process locks
  are recovered by Qt after interruption. WebEngine pages are destroyed before
  their persistent profile to release its cache and storage cleanly.

## Contracts Kept

New Canvas, Import JSON, Open Project, Tutorial reset, project folder access,
project discovery/previews, and output notifications retain their existing KFPS
service interfaces. The editor retains its controls, shape identities, native
text, masks, reference images, guides, groups, clipboard, history, export checks,
file inputs, and download fallback. No live-game import/export code was changed.

Projects remain in `runtime/fabric-editor/projects`; exports remain in
`imgs/editor`; recovery remains in `runtime/fabric-editor/autosave.json`.
Preferences use the existing `preferences.json`, with a bounded allowlist of
settings. Theme-only legacy requests remain supported. Atomic writes preserve
unrelated preferences; failures retain pending client changes for retry.

The desktop profile cannot automatically read favorites or shortcuts stored only
inside a previous external browser profile. Project files and existing server-side
theme/recovery data are unaffected. No external browser profile is scanned.

## Build

From the repository root, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/native_launcher/build_launcher.ps1 -Editor
```

The existing launcher source is compiled with `KFPS_EDITOR`; the normal KFPS
launcher is not replaced. Both bundled Python and the established system-Python
fallback continue to work. `--runtime-root` can isolate development editor state.

## Update Safety And Release Gate

KFPS refuses to start an update while its editor is open. On Windows, the editor
also holds the signed updater's existing exclusive installation lock, preventing
even the current updater from replacing an open editor's files. The legacy update
process-stop helper refuses to kill an independent editor with unsaved work.

The full release places `KFPS Editor.exe` beside `KFPS.exe` and `KFPS-Updater.exe`
at the bundle root. Matching copies also live inside `KloudysFH6Painter` for the
existing inner-folder launch and repair layout.

Bootstrap updater 1.0.3 adds that exact outer editor filename to its allowlist.
Publication requires minimum bootstrap 1.0.3 whenever that file is managed, so
older updaters verify and hand off to the new updater before reading the new
payload. New installs, missing-launcher repair, and interrupted creation or
replacement use the existing transaction and rollback mechanism. No general
executable allowlist or signature bypass is introduced.

## Themes And Dialogs

Blackout and Whiteout are flat neutral presets with readable text and control
boundaries. Theme adjustment exposes six primary colors, live text contrast
status, a starting-theme selector and Reset colors; all previous color settings
remain under More colors. Existing custom themes remain readable. New custom
themes optionally record their built-in base, preserving matte surfaces after
restart. Preview and Cancel do not change the persisted selection.

Naming prompts confirm with Enter and retain explicit Cancel/Escape behavior.
Canvas shortcuts are suspended behind open dialogs. Custom layer names survive
project reloads. Explicit project, export and theme saves have bounded requests;
failed project saves retain unsaved status and allow retry.

## Validation

Development evidence is indexed in the external `Editor Desktop Host 2026-09-09`
report. It includes actual cold launcher runs, KFPS-client process exit, all 1,400
native shape pixel/export comparisons, 17 editor regression scripts, 3,000-layer
save/export/recovery and renderer interruption, native close choices, downloads,
and favorites added/removed through the UI across full process restarts and a
forced port collision. These are local Windows development tests, not a claim of
production validation on every supported Windows/runtime combination.

Hosting alone is not a measured frame-rate improvement. Fabric's existing heavy
workload stalls remain a separate performance-hardening task.
