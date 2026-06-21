# KFPS WPF Prototype

This is the first native Windows shell for KFPS. It intentionally does not replace
the generator, importer, exporter, updater, or Fabric editor yet.

## Current Scope

- Native WPF main window with left navigation.
- Dashboard, Generate, Import/Export, Editor, Image Tools, Tutorial, Bug Reports, and Settings screens.
- Process log panel.
- Buttons that call the existing KFPS batch/Python tools.
- App-root detection by walking up to `VERSION` and `KloudysGalateaGenesis.exe`.
- Repeatable WPF screenshot capture using `--screenshot-all`.

## Design Direction

The WPF app should become the stable native control surface around existing tools
before any backend logic is ported. This prevents a full rewrite from breaking
working generation/import/export behavior.

The current layout intentionally avoids scroll containers inside workflow pages.
It uses a workbench model instead of stacked tabs: slim tool rail, contextual left
controls, central output canvas, right inspector, and compact log strip.

Reference direction used for this pass:

- Figma: dark canvas-first workspace, thin side panels, strong center document area.
- Spline: compact top controls, central creative viewport, contextual inspector.
- Nothing X: sparse high-contrast modules, restrained labels, fewer visible controls.

Rules from those references:

- One primary work area at a time.
- No nested cards, no dashboard bento clutter, no large rounded buttons.
- Settings live in the left context panel or right inspector, not scattered across tabs.
- The preview/workbench is visually dominant.
- Utility text is small and precise; actions are short and obvious.

Recommended migration order:

1. Dashboard and tutorials.
2. JSON browser and generated/editor/exported folders.
3. Generator queue and preview display.
4. Import/export command orchestration.
5. Settings/theme persistence.
6. Optional backend porting only after the native shell is proven.

## Build

From the repository root on Windows:

```powershell
dotnet build .\KFPS.Wpf\KFPS.Wpf.csproj -c Release
```

Run:

```powershell
dotnet run --project .\KFPS.Wpf\KFPS.Wpf.csproj
```

Render all main workflow pages to PNG for visual QA:

```powershell
dotnet run --project .\KFPS.Wpf\KFPS.Wpf.csproj -- --screenshot-all
```

Screenshots are written to:

```text
runtime\wpf-screenshots\<timestamp>\
```

Publish a top-level prototype launcher folder:

```powershell
.\KFPS.Wpf\publish-root-launcher.ps1
```

This creates `KFPS Native Launcher\KFPS.exe` beside the existing app files. It
does not replace the current root launcher until we explicitly decide to do that.
