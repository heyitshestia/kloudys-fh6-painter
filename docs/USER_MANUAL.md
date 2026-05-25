# User Manual

This manual covers the normal launcher-first workflow for Kloudy's FH6 Painter.

## 1. Install And Launch

Use **64-bit Python 3.12**. Start from:

```text
Kloudys Painter Launcher.exe
```

If you are using the source folder instead of the standalone launcher executable, start from:

```text
00_launcher.bat
```

For a fresh install, click these launcher buttons in order:

1. `Setup Python`
2. `Install Dependencies`
3. `Launch App`

Manual batch files are still available, but the launcher is the intended entry point. If setup looks broken, run `05_check_environment.bat`.

## 2. Generate Final Vinyl

1. Open `Generate Final Vinyl`.
2. Choose one source image.
3. Pick a Kloudy preset.
4. Optional: enable `Tune this run` to override layers, resolution, samples, or finalize points.
5. Keep `Luma Prep` and `Edge Repair` enabled unless the source looks better without them.
6. Click `Generate Final Vinyl`.
7. Wait for `FINALIZE CHECKPOINTS COMPLETE`.

Generation has two separate phases:

| Phase | What happens | User action |
| --- | --- | --- |
| Internal build | The patched GPU builder creates raw checkpoints. These are source material for finalization. | Wait. Do not import these unless debugging. |
| Finalize Checkpoints | The app scores checkpoints, caps them to safe layer counts, applies Edge Repair, writes previews, and creates import-ready final JSONs. | Keep waiting until completion. |

The internal builder may finish before final files are ready. Do not close the app until Finalize Checkpoints completes.

You can tell the app is still working when:

- The button still says `Stop after next saved point`.
- The log is printing `Finalize Checkpoints`, `Edge Repair`, scoring, report, or preview messages.
- New files are still appearing in the run folder.

The run is done when the log says:

```text
FINALIZE CHECKPOINTS COMPLETE
```

New runs are saved under:

```text
imgs/generated/<job>/
```

Each new duplicate run becomes `<job>v2`, `<job>v3`, etc.

## 3. Output Folder Contract

New generation folders are organized like this:

| Folder | Purpose |
| --- | --- |
| `finals/` | Import-ready finalized JSON files. This is what normal users import. |
| `checkpoints/` | Internal raw generator checkpoints. These are diagnostic/source files, not the normal import target. |
| `previews/` | Raw and finalized preview PNGs, plus Luma Prep images. |
| `reports/` | Run metadata, effective settings, candidate scores, and temporary V2 settings. |

The app still scans older legacy folders so previous generated runs remain importable after updating.

## 4. Kloudy Presets

Presets are a simple speed-to-quality ladder:

| Preset | Target layers | Best for | Notes |
| --- | ---: | --- | --- |
| `Fast & Ugly` | 1000 | Quick composition checks and rough drafts. | Fastest option. Use it to test crop, source quality, and overall placement. Do not expect final quality. |
| `Okay Draft` | 1500 | Useful test imports without a long wait. | Good for checking scale and whether FH6 import behaves correctly. |
| `Pretty Good` | 2000 | Recommended everyday balance. | Start here for most real images. |
| `Slow & Beautiful` | 3000 | Final-quality runs when time matters less. | Best bundled quality target. Use for sources worth waiting on. |

The sample budgets are tuned for the patched faster generator, so these presets are intentionally stronger than the old upstream/Bvz-style presets.

If you are unsure, use `Pretty Good`. If the image is just a test, use `Fast & Ugly` or `Okay Draft`. If the image is a final livery piece, use `Slow & Beautiful`.

## 5. Tune This Run

Custom run fields override the selected preset only for that run.

| Setting | Meaning |
| --- | --- |
| `Template layers` | Target template size. FH6 still reserves 4 boundary layers during import. |
| `Max resolution` | Largest image side used by generation. Higher can preserve detail but costs time. |
| `Random samples` | Main search effort. Higher usually improves accuracy. |
| `Mutated samples` | Local refinement effort around promising shapes. |
| `Finalize at layers` | Layer counts that become finalized import choices. |

If an image is inaccurate, increase random samples first.

## 6. Luma Prep

`Luma Prep` creates a luminance-banded intermediate image before the internal build. It keeps transparency and usually helps flat/anime-style images separate clean regions.

Turn it off for soft gradients or photos where banding makes the result worse.

## 7. Edge Repair

`Edge Repair` runs during finalization. It targets border mess, transparent holes, fingers, hair gaps, cutout edges, and similar problem areas.

It is enabled by default because it usually improves import-ready final JSONs.

## 8. vroom vroom scrrrrt zoooom!

This switch doubles `Random samples` and `Mutated samples`.

It does not double template layers, max resolution, preview size, or output layer count.

## 9. Pick A Final JSON

Open `Import Final JSON`.

The browser is organized as:

```text
Generated vinyl run -> Finalized checkpoint -> Preview -> Import
```

Rules:

- The newest run is selected automatically.
- Duplicate generations stay separate.
- The best safe final JSON is listed first.
- The highlighted finalized checkpoint is the one that will be imported.
- Raw internal checkpoints are hidden from the normal picker.
- Manual JSON selection still exists for debugging or older files.

Pick the checkpoint by looking at the preview and shape count. Higher shape counts are not always better if the preview is messier, so the browser lets you choose instead of forcing the app's recommendation.

## 10. Prepare FH6 For Import

1. Start Forza Horizon 6.
2. Open `Create Vinyl Group` or `Vinyl Group Editor`.
3. Load or create a template with enough simple layers.
4. Ungroup the template.
5. Stay in the editor and do not switch menus.
6. Remember the exact layer count shown by the game.

## 11. Import Final JSON Into FH6

1. Open `Import Final JSON`.
2. Refresh/select the FH6 process.
3. Enter the exact template layer count.
4. Pick a finalized checkpoint.
5. Click `Import Final JSON into FH6`.

The app verifies the FH6 template before writing. If verification fails, it stops before import.

During import, keep FH6 focused on the Vinyl Group Editor. Do not switch tabs, open apply/livery menus, or click around while the app is writing layers.

If import reports an ungroup/template error, the usual causes are:

- The group is not actually ungrouped.
- FH6 is in the wrong menu.
- The template layer count is wrong.
- The active editor group is not the prepared template.
- The app does not have permission to write to the FH6 process.

## 12. FH6 Boundary Layers

FH6 needs 4 non-art boundary layers for correct cover/apply behavior.

Usable drawable count:

```text
template layers - 4
```

Examples:

| Template layers | Usable drawable layers |
| ---: | ---: |
| 500 | 496 |
| 1000 | 996 |
| 2000 | 1996 |
| 3000 | 2996 |

## 13. App Areas

| Area | Purpose |
| --- | --- |
| `Generate Final Vinyl` | Builds source art into finalized import-ready vinyl JSONs. |
| `Import Final JSON` | Imports a finalized JSON into an open FH6 vinyl group. |
| `FH6 Tools` | Diagnostics and locator utilities for import troubleshooting. |
| `Tutorial` | Short in-app workflow reminder. |
| `Settings` | Theme and app appearance. |

## 14. Troubleshooting

### App does not open

Run these in order:

```text
01_add_python312_to_path.bat
02_install_dependencies.bat
05_check_environment.bat
```

### Preview unavailable

Install dependencies again. Generation and import may still work even if preview rendering fails.

### GPU or OpenCL error

Update the NVIDIA, AMD, or Intel GPU driver. The builder uses OpenCL.

### Import says ungroup error

Check that you are in Vinyl Group Editor, the template is ungrouped, the exact template layer count is entered, and you did not switch menus after preparing the template.

### Import permission error

Close the app and run `04_start_app.bat` as administrator.

### Output is too blurry

Use more layers, more random samples, `Pretty Good` or `Slow & Beautiful`, or a larger template.

### Output has edge halos

Keep `Edge Repair` on. Try `Luma Prep` on for flat art or off for soft sources.
