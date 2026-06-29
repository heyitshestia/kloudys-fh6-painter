# KFPS Native QML Interface

This directory contains the PySide6/Qt Quick desktop interface. It changes presentation and orchestration only: the KFPS generator, finalizer, game-memory importer/exporter, JSON renderer, updater, and Fabric editor remain the existing backend implementations.

## Source launch

Use 64-bit Python 3.12:

```powershell
python -m pip install -r requirements.txt
python KFPS.UI\app.py
```

The app starts at approximately `1548×970`, adapts down to `1140×720`, and uses a wide sidebar on normal displays with an automatic compact rail on constrained windows.

## Current refinement baseline

The first geometry refinement pass standardizes centered button content, field alignment, logical scaling breakpoints, stacked dashboard sizing, and route-aware sidebar scrolling. See `docs/REFINEMENT_PASS_01.md` and `Previews/refinement-pass-01/`.

## Build KFPS.exe

```powershell
powershell -ExecutionPolicy Bypass -File tools\native_launcher\build_launcher.ps1
```

The shipped executable is intentionally small. It only finds the bundled Python runtime and launches `KFPS.UI\app.py` from loose source files. Copy the output `KFPS.exe` beside the `KloudysFH6Painter` folder, and keep the same launcher payload inside `KloudysFH6Painter\KFPS.exe` so the updater can repair the parent launcher.

## Structure

- `qml/` — the entire interface and reusable visual system
- `assets/` — original Night Blossom artwork and SVG icons
- `src/kfps_ui/` — small Python services exposed to QML
- `bridges/` — thin subprocess adapters to the unchanged backend
- `tests/` — non-destructive service tests
- `tools/` — screenshot and visual-QA helpers
- `docs/` — architecture, behavior, build, and validation notes

See `docs/ARCHITECTURE.md` before changing application state or process handling.
