# Kloudy's FH6 Painter

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
- bundled GPU generator: `KloudysGeneratorV4.exe`
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
7. Leave `Edge Repair` enabled.
8. Click `Generate Final Vinyl`.
9. Wait until the log says `FINALIZE CHECKPOINTS COMPLETE`.
10. Open FH6 and prepare an ungrouped vinyl template with enough layers.
11. Open `Import Final JSON`.
12. Pick a finalized checkpoint.
13. Enter the exact FH6 template layer count.
14. Click `Import Final JSON into FH6`.

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
| `Flat Colors / Logos` | logos, decals, hard borders, mascot art, clean color regions | on | edge-biased |
| `Shaded Character Art` | anime, characters, skin, hair, eyes, mixed linework | off | character-art weighting |
| `Smooth Gradients` | glossy shading, soft transitions, dark-to-light gradients | off | soft detail |

If you are unsure, start with `Shaded Character Art`.

### Tune This Run

`Tune this run` lets you override the chosen preset without editing files.

The most important settings are:

- `Template layers`: how many FH6 layers your target group has.
- `Max resolution`: largest image side used by generation.
- `Random samples`: main search effort.
- `Mutated samples`: local refinement around promising shapes.
- `Finalize at layers`: checkpoints that become final import choices.

Higher samples usually improve quality but take longer.

### Luma Prep

`Luma Prep` creates a luma-banded intermediate image before generation.

Use it for flat/logos/hard regions. Leave it off for soft gradients, tiny face details, and most shaded character art unless testing proves otherwise.

### Edge Repair

`Edge Repair` is default-on. It runs after raw generation and tries to clean borders, transparent holes, fingers, hair gaps, and cutout edges.

Keep it on unless you are debugging.

### vroom vroom scrrrrt zoooom!

This switch doubles random samples and mutated samples. It does not double layer count or resolution.

Use it when you want more search effort without changing the output layer target.

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

FH6 import needs extra non-art layers for mask/bounds behavior.

Default safe mode reserves 4 mask layers:

```text
usable drawable layers = template layer count - 4
```

Examples:

| FH6 template layer count | Usable drawable layers |
| ---: | ---: |
| 500 | 496 |
| 750 | 746 |
| 1000 | 996 |
| 1500 | 1496 |
| 2000 | 1996 |
| 3000 | 2996 |

If the JSON has more shapes than the usable count, the app will cap/trim during finalization or import.

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

## Common Problems

| Problem | Most likely fix |
| --- | --- |
| App does not start | Open launcher, run `Setup Python`, then `Install Dependencies`. |
| Preview unavailable | Run `02_install_dependencies.bat` or launcher `Install Dependencies`. |
| GPU/OpenCL error | Update NVIDIA/AMD/Intel GPU driver. |
| FH6 process not found | Start FH6, open Vinyl Group Editor, then click Refresh. |
| Import says ungroup/template error | You are likely in the wrong FH6 menu, wrong group, wrong layer count, or the template is not ungrouped. |
| Located table is stale/null | Re-open the correct vinyl group, remove duplicate groups/templates above it, and run auto-locate again. |
| Output is soft | Use more layers/samples, keep Luma Prep off for soft/character art, and pick the checkpoint visually. |
| Borders have halos | Keep Edge Repair on; try Flat Colors / Logos with Luma Prep for hard art. |

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
| Sam Twidale | https://samcodes.co.uk/ | `geometrize-lib` author; original geometry approximation work credited by the upstream license. |
| Michael Fogleman | https://github.com/fogleman/primitive | `primitive` author; original primitive-based image approximation library credited by the upstream license. |
| Sanguk Ko / ree9622 | https://github.com/ree9622 | Korean localization contributor in upstream history. |
| heyitshestia / Kloudy | https://github.com/heyitshestia/kloudys-fh6-painter | This fork: launcher-first workflow, PySide app, style presets, Luma Prep, Edge Repair defaults, finalized-run browser, updater workflow, release packaging, and FH6 safety adjustments. |

## Limitations

- FH6 import requires Windows and a running FH6 process.
- Import may require running the app as administrator.
- GPU generation requires working OpenCL support.
- The normal importer is optimized around the currently supported generated-shape path.
- Universal handmade multi-shape import is not complete.
- In-game FH6 editor state matters. If FH6 is in the wrong menu, import will fail even if the JSON is valid.

## License

This project is a derivative of the Forza Painter workflow and keeps the original MIT license notices in [LICENSE](LICENSE) and [LICENSE.geometrize-gpu](LICENSE.geometrize-gpu).
