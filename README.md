# Kloudy's FH6 Painter

<p align="center">
  <img src="docs/images/repo-banner.png" alt="Kloudy's FH6 Painter banner" width="100%">
</p>

[English](README.md) | [中文](README.zh-CN.md)

Kloudy's FH6 Painter turns source art into finalized Forza Horizon 6 vinyl JSON, then imports that JSON into an open FH6 Vinyl Group Editor template.

This README is the readable start-here guide. The full detailed manual is in [docs/USER_MANUAL.md](docs/USER_MANUAL.md). The very detailed FH6 group/import guide is in [docs/FH6_IMPORT_GUIDE.md](docs/FH6_IMPORT_GUIDE.md).

## What You Download

For normal users, download the latest release zip:

```text
Kloudys-FH6-Painter-<version>.zip
```

The standalone release contains:

- `Kloudys Painter Launcher.exe`
- `KloudysFH6Painter/`
- bundled Python 3.12 runtime
- bundled Python dependencies
- bundled GPU generator: `KloudysGeneratorV5.exe`
- `Images/` folder next to the launcher for your source art

You should not need to install Python manually when using the standalone release. The setup buttons are still there as a fallback.

## First Launch

Start here:

```text
Kloudys Painter Launcher.exe
```

If you are using the source folder instead of the standalone release, start here:

```text
00_launcher.bat
```

The launcher checks whether Python and dependencies are usable, checks GitHub `main` for updates, and opens the painter app.

<img src="docs/screenshots/launcher-overview-annotated.png" width="900" alt="Kloudy's FH6 Painter launcher with numbered setup buttons">

### Launcher Buttons

| Button | Use it when | What it does |
| --- | --- | --- |
| `Setup Python` | Python is missing or broken. | Finds or installs 64-bit Python 3.12 and adds it to PATH. |
| `Install Dependencies` | App says dependencies are missing. | Installs the Python packages needed by the app, previews, importer, and launcher. |
| `Update` | Launcher says an update is available. | Runs the GitHub updater and syncs app files from `main`. |
| `Launch App` | Setup is green or ready. | Opens the actual painter app. |

If something is broken, run this from inside `KloudysFH6Painter/`:

```text
05_check_environment.bat
```

## Fast Workflow

1. Put your source image in the `Images/` folder next to the launcher.
2. Open `Kloudys Painter Launcher.exe`.
3. Click `Launch App`.
4. Open `Generate Final Vinyl`.
5. Click `Choose source image`.
6. Pick a preset.
7. Set `Template layers` to the FH6 template size you plan to use.
8. Click `Generate Final Vinyl`.
9. Wait until the log says `FINALIZE CHECKPOINTS COMPLETE`.
10. Open FH6 and load your saved 3000-layer plain white circle template.
11. If you just created that template, save it once, leave/reopen it, then ungroup it.
12. Open `Import Final JSON`.
13. Pick a finalized checkpoint.
14. Enter `3000` as the exact FH6 template layer count.
15. Click `Import Final JSON into FH6`.

The important part: generation is not done when the GPU generator finishes. The final import files are ready only after Finalize Checkpoints finishes.

## Generate Final Vinyl

The Generate tab creates the vinyl.

<img src="docs/screenshots/app-generate-workflow-annotated.png" width="900" alt="Generate Final Vinyl tab with numbered controls">

### Source Art

Use one image at a time. Good source images matter. Transparent PNGs usually work best because the app can respect the cutout shape.

Supported normal inputs include PNG, JPG, JPEG, BMP, and similar formats Pillow/OpenCV can read.

### Presets

Current stock presets are style-based, not the old fast/slow ladder:

| Preset | Best for | Luma Prep default | Shape style |
| --- | --- | --- | --- |
| `Shaded Character Art` | anime, characters, skin, hair, eyes, mixed linework | off | character-art weighting |
| `Flat Colors` | stickers, mascot art, hard borders, clean color regions | on | edge-biased |
| `Smooth Gradients` | glossy shading, soft transitions, dark-to-light gradients | off | soft detail |

If you are unsure, start with `Shaded Character Art`.

### Automatic Settings And Pro Settings

By default, the Generate tab only asks for the settings normal users should touch:

- `Template layers`: how many FH6 layers you want to build for.
- `Finalize at layers`: which checkpoints should become final import choices.

The app calculates the rest automatically from the source image, visible alpha area, edge/detail density, preset, and target layer count.

Enable `Pro settings - manual samples/resolution` only if you want direct control over:

- `Max resolution`: how much detail the generator can see.
- `Random samples`: broad shape-search effort.
- `Mutated samples`: local fit/refinement effort.
- `2x Sample Goblin`: doubles random and mutated samples for a slower but deeper search.
- `Luma Prep`: luma-banded preprocessing for broad clean regions.
- `Edge Repair`: finalization cleanup for borders, holes, and transparent cutouts.

The app remembers whether Pro settings were open, and it remembers your Pro values across restarts.

### Luma Prep

`Luma Prep` creates a luma-banded intermediate image before generation.

Use it for flat regions, stickers, and hard color art. Leave it off for soft gradients, tiny face details, and most shaded character art unless testing proves otherwise.

### Edge Repair

`Edge Repair` runs after raw generation and tries to clean borders, transparent holes, fingers, hair gaps, and cutout edges.

Keep it on unless you are debugging. It is inside Pro settings because most users should not need to touch it.

### 2x Sample Goblin (slower)

This switch doubles random samples and mutated samples. It does not double layer count or resolution, and it usually takes longer.

Use it when you want more search effort without changing the output layer target. It is inside Pro settings.

## Import Final JSON

The Import tab is a finalized JSON browser plus FH6 importer.

<img src="docs/screenshots/app-import-json-browser-annotated.png" width="900" alt="Import Final JSON tab with numbered controls">

The browser is organized like this:

```text
Generated run folder -> Finalized checkpoint -> Preview -> Import
```

Rules:

- The newest run appears first.
- Duplicate generations are kept as separate folders, such as `image`, `imagev2`, `imagev3`.
- Raw generator checkpoints are not the normal import target.
- Normal users should import files from `finals/`.
- The highlighted finalized checkpoint is the one that imports.
- `Use best safe final` selects the best scored checkpoint that fits the import budget.
- You can still manually choose a JSON for debugging or older files.

## FH6 Template Rule

Default import uses the full template for art layers.
Finalize Checkpoints keeps transparent-source shapes inside the PNG canvas, so normal imports do not need FH border masks.
Legacy 4-mask import remains available in Settings as a fallback test mode, but it can make underlying stacked vinyls transparent.

Default usable layer count:

```text
usable drawable layers = template layer count
```

Examples:

| FH6 template layer count | Usable drawable layers |
| ---: | ---: |
| 500 | 500 |
| 750 | 750 |
| 1000 | 1000 |
| 1500 | 1500 |
| 2000 | 2000 |
| 3000 | 3000 |

If the JSON has more shapes than the template count, the app will cap/trim during finalization or import.

Full FH6 setup instructions are in [docs/FH6_IMPORT_GUIDE.md](docs/FH6_IMPORT_GUIDE.md).

## Update Correctly

Use the launcher `Update` button, or run:

```text
03_update_from_github.bat
```

Close the app before updating.

Do not update by dragging random files into the folder. The updater preserves generated/runtime data and syncs program files from GitHub.

Update logs and backups are stored here:

```text
runtime/update-logs/
runtime/update-backups/
```

## Output Folders

Each generation creates a run folder:

```text
imgs/generated/<job-name>/
```

Inside it:

| Folder | Meaning |
| --- | --- |
| `checkpoints/` | raw internal generator JSONs |
| `finals/` | import-ready finalized JSONs |
| `previews/` | preview PNGs |
| `reports/` | settings, scores, metadata, and finalization details |

Normal users import from `finals/`.

## Luma Band Pass Tab

The standalone `Luma Band Pass` tab lets you choose one image and preview before/after luma banding without running a full generation.

Output goes here:

```text
imgs/luma-bands/
```

This is useful for deciding whether Luma Prep helps or hurts a source image before spending time on a full run.

## Image Tools Tab

The `Image Tools` tab collects external browser tools that are useful before generation:

| Tool | Use |
| --- | --- |
| `Background Remover` | Opens PhotoRoom's online background remover for transparent cutouts. |
| `2x / 4x Browser Upscaler` | Opens a local-in-browser upscaler that can enlarge small sources before generation. |
| `Browser Downscaler / Compressor` | Opens Squoosh for clean resizing, format conversion, and compression. |

These tools are links only. They do not upload anything through the app itself.

## Image Size Helper Tab

The `Image Size Helper` tab lets you choose one image and shows:

- current width x height in pixels
- current megapixels
- same-aspect resize targets from `1 MP` through `6 MP`
- quick recommended MP ranges for each stock preset

Use it before upscaling/downscaling when you want a source size that fits the preset.

## Import / Export Handmade JSON

The `Import Handmade JSON` tab is the experimental universal FH6 shape importer/exporter.

It is intended for handmade/exported JSONs that contain real FH shape type codes, not only the generated ellipse/rectangle path.

Current workflow:

1. Open FH6 Vinyl Group Editor.
2. Load your saved 3000-layer plain white circle template.
3. If you just created it, save it once, leave/reopen it, then ungroup it.
4. Choose the handmade JSON in the app.
5. Import it.
6. Save and reload the vinyl group before judging the final result.

Important WIP notes:

- Save/reload is currently needed before the imported shapes display correctly.
- A strange vinyl thumbnail in the FH6 menu is normal right now.
- Both the live-editor display refresh and thumbnail behavior are still being worked on.
- The importer trims the live group count after import, so one saved 3000-circle template can be reused and culled down to the final layer count.
- The exporter is read-only. It exports the currently loaded/open FH6 group into a compatible JSON using the live layer count you enter.

## Common Problems

| Problem | Most likely fix |
| --- | --- |
| App does not start | Open launcher, run `Setup Python`, then `Install Dependencies`. |
| Preview unavailable | Run `02_install_dependencies.bat` or launcher `Install Dependencies`. |
| GPU/OpenCL error | Update NVIDIA/AMD/Intel GPU driver. |
| FH6 process not found | Start FH6, open Vinyl Group Editor, then click Refresh. |
| Import says ungroup/template error | You are likely in the wrong FH6 menu, wrong group, wrong layer count, or the template is not ungrouped. |
| Located table is stale/null | Re-open the correct vinyl group, remove duplicate groups/templates above it, and run auto-locate again. |
| Output is soft | Use the right preset, more layers, Pro settings with more samples if needed, keep Luma Prep off for soft/character art, and pick the checkpoint visually. |
| Borders have halos | Keep Edge Repair on; try Flat Colors with Luma Prep for hard flat art. |

The deep troubleshooting section is in [docs/USER_MANUAL.md](docs/USER_MANUAL.md#troubleshooting).

## Examples

Source and result examples are included in [docs/examples/test-finest](docs/examples/test-finest).

| Source | Generated result |
| --- | --- |
| <img src="docs/examples/test-finest/miku-original.png" width="360" alt="Miku source"> | <img src="docs/examples/test-finest/miku-vinyl.png" width="360" alt="Miku vinyl result"> |
| <img src="docs/examples/test-finest/pokemon-original.png" width="360" alt="Pokemon source"> | <img src="docs/examples/test-finest/pokemon-vinyl.png" width="360" alt="Pokemon vinyl result"> |

## Credits

This project is built on top of earlier Forza Painter work. License notices are kept in [LICENSE](LICENSE) and [LICENSE.geometrize-gpu](LICENSE.geometrize-gpu).

| Person / project | Link | Contribution |
| --- | --- | --- |
| AE / A-Dawg#0001 | https://github.com/forza-painter/forza-painter | Original Forza Painter project, MIT-licensed FH import workflow, memory-writing/import foundation, and geometry-to-vinyl approach. |
| BVZRays / bvz rays | https://github.com/bvzrays/forza-painter-fh6 | FH6-focused desktop fork and upstream work for FH6 UI, importer/locator behavior, app packaging, and workflow ideas. |
| zjl88858 / forza-painter-geometrize-gpu | https://github.com/zjl88858/forza-painter-geometrize-gpu | GPU/OpenCL geometrize generator lineage used by the bundled generator workflow. |
| Community FH5 shape-code spreadsheet | https://docs.google.com/spreadsheets/d/1zmdme-c1ZqxTw8dd-ooYhJV8aOSYc1LkZlmIfELRbqo/edit#gid=0 | Shape-code ordering and names used as the starting point for FH6 universal-shape registry work. |
| Frozander | Discord | Shared the practical page/offset observation that FH6 shape pages follow the FH5 ordering with offset/page changes, which helped guide the registry inference. |
| FH painter / modding Discord testers | Discord | Live templates, screenshots, crash/save reports, and shape-order checks used to validate the handmade importer behavior. |
| Sam Twidale | https://samcodes.co.uk/ | `geometrize-lib` author; original geometry approximation work credited by the upstream license. |
| Michael Fogleman | https://github.com/fogleman/primitive | `primitive` author; original primitive-based image approximation library credited by the upstream license. |
| Sanguk Ko / ree9622 | https://github.com/ree9622 | Korean localization contributor in upstream history. |
| heyitshestia / Kloudy | https://github.com/heyitshestia/kloudys-fh6-painter | This fork: launcher-first workflow, PySide app, style presets, Luma Prep, Edge Repair defaults, finalized-run browser, updater workflow, release packaging, FH6 safety adjustments, 3000-template layer culling, and custom FH6 handmade/universal importer completion. |

### Custom Importer Work

The handmade/universal importer was completed in this fork by combining community shape-code information with live FH6 memory validation.

Confirmed implementation details:

- FH6 primitive selection uses the 16-bit shape word at layer offset `0x7A`.
- The importer writes only save-safe layer fields: position, scale, rotation, skew, color, mask flag, and shape word.
- The exporter reads the same save-safe fields from the currently open FH6 group and writes them to a compatible JSON.
- Volatile render/cache fields and resource pointers are intentionally not copied.
- A saved/reopened 3000-layer plain white circle template is the recommended reusable base for imports.
- After import, the app trims the FH6 group count and table end so the saved vinyl uses only the actual layer count.
- A 13-tab / 520-shape FH6 registry was built from confirmed tab anchors plus sheet-backed and inferred shape ordering.

The custom importer license and attribution notice is in [LICENSE.custom-importer](LICENSE.custom-importer).

## Limitations

- FH6 import requires Windows and a running FH6 process.
- Import may require running the app as administrator.
- GPU generation requires working OpenCL support.
- The normal importer is optimized around the currently supported generated-shape path.
- Universal handmade multi-shape import is working but still marked WIP because live editor refresh and vinyl-menu thumbnail behavior are not fully polished.
- In-game FH6 editor state matters. If FH6 is in the wrong menu, import will fail even if the JSON is valid.

## Discord
https://discord.gg/CHkAQeWM
its not my server, please don't spam, please behave.
A bit of technical literacy is a hard requirement for all of this, there will be no "how do i download this" hand in hand walkthroughs on discord.
## License

This project is a derivative of the Forza Painter workflow and keeps the original MIT license notices in [LICENSE](LICENSE) and [LICENSE.geometrize-gpu](LICENSE.geometrize-gpu).
The custom handmade/universal importer is MIT-licensed with its own attribution notice in [LICENSE.custom-importer](LICENSE.custom-importer).
