# User Manual

This manual explains the normal user workflow for Kloudy's FH6 Painter.

## 1. Install

Use **64-bit Python 3.12**. Other Python versions may work for parts of the app, but Python 3.12 is the expected version.

Recommended:

```text
00_launcher.bat
```

The launcher shows setup status, GitHub update status, and the main launch button. For a fresh install, click:

1. `Setup Python`
2. `Install Dependencies`
3. `Launch App`

Manual setup is also available:

1. In this project folder, run:

```text
01_add_python312_to_path.bat
```

2. Then run:

```text
02_install_dependencies.bat
```

3. Start the launcher/app flow:

```text
04_start_app.bat
```

If setup looks broken, run:

```text
05_check_environment.bat
```

## 2. Generate JSON

1. Open the `Generate JSON` tab.
2. Choose one image.
3. Pick a quality preset.
4. Optional: enable `Use custom settings` and override the preset.
5. Optional: enable or disable `Luma Bands`, `Targeted repair`, and `vroom vroom scrrrrt zoooom!`.
6. Click `Start generating`.
7. Wait for checkpoints, previews, and final V2 JSON files.

Generated files are saved under `imgs/generated/...`.

## 3. Presets

The active preset list is intentionally simple:

| Preset | Output layers | Random samples | Mutated samples | Max resolution |
| --- | ---: | ---: | ---: | ---: |
| Extremely fast | 500 | 30000 | 1000 | 600 |
| Fast | 1000 | 60000 | 2000 | 900 |
| Balanced | 1800 | 120000 | 5000 | 1400 |
| Slow | 2500 | 220000 | 8000 | 2000 |
| Super slow | 3000 | 350000 | 12000 | 2400 |

Higher presets usually look better, but they take longer.

## 4. Custom Settings

Custom settings override the selected preset for the current run.

Important fields:

| Setting | Meaning |
| --- | --- |
| Output layers | Target drawable shape count before FH6 boundary trimming. |
| Max resolution | Largest image side used by generation. Higher can preserve detail but costs time. |
| Random samples | Main quality search effort. Higher usually improves accuracy. |
| Mutated samples | Local refinement effort around promising shapes. |
| Save checkpoints | Which layer counts are saved during generation. |

If the image is soft or inaccurate, increase random samples first.

## 5. Luma Bands

`Luma Bands` is a preprocess pass.

It creates a new temporary image from the input, bands the luminance values, keeps transparency, and sends that processed image to the generator.

Use it for:

- anime art
- clean flat colors
- images with noisy midtones
- sharper region separation

Turn it off for:

- soft gradients
- photos where smooth shading matters
- sources where banding makes the image worse

## 6. Targeted Repair

`Targeted repair` runs after raw generation.

It tries to improve difficult areas without changing the whole generation strategy:

- transparent holes
- border halos
- hair cutouts
- fingers and small gaps
- sharp edges

It is enabled by default because it usually improves FH6 vinyl edges.

## 7. vroom vroom scrrrrt zoooom!

This switch doubles effort-style numeric settings for the selected preset.

It does not double:

- output layers
- max resolution
- preview size

It is useful when you want more search effort without changing the template size.

## 8. Checkpoints And Reports

V2 writes checkpoints and reports for each run.

Common files:

| File | Meaning |
| --- | --- |
| `*.250.json`, `*.1000.json`, etc. | Raw checkpoint JSON. |
| `*v2.json` | V2 processed JSON for a checkpoint. |
| `*.v2.final.*.json` | Final selected V2 output. |
| `*.preview.*.png` | Preview image for a checkpoint. |
| `*.v2.report.json` | Run metadata, settings, candidates, and selected output. |

The checkpoint browser scans the `imgs` folder on startup, so older generated runs are still available after restarting the app.

The import tab groups generated JSON by run:

- `Latest run` is selected automatically after a new generation.
- `Previous run` entries are older duplicate generations of the same image.
- The recommended import-safe JSON is shown first.
- Raw overshoot files that exceed the import budget are marked and skipped by the `Use selected` button.

## 10. Utility Files And App Areas

Common files users may run:

| File | Purpose |
| --- | --- |
| `00_launcher.bat` | Opens the setup/update launcher. Recommended entry point. |
| `01_add_python312_to_path.bat` | Adds Python 3.12 and Scripts paths to the user PATH. |
| `02_install_dependencies.bat` | Installs required Python packages. Run this before using the app. |
| `03_update_from_github.bat` | Updates app files from GitHub while preserving generated/runtime data. |
| `04_start_app.bat` | Starts the launcher/app flow. |
| `05_check_environment.bat` | Checks Python and dependency status. |
| `99_clean_runtime_data.bat` | Removes generated cache/runtime data before packaging or troubleshooting. |

Main app areas:

| Area | Purpose |
| --- | --- |
| `Generate JSON` | Generates checkpoints, V2 JSON, previews, and reports from one source image. |
| `Import` | Imports a generated JSON into an open FH6 vinyl group. |
| `Generated-run browser` | Browses generated runs and sorted checkpoints from `imgs`, with recommended JSON first. |
| `Shape dumps` | Experimental helper for dumping single-layer shape memory while researching handmade shape compatibility. |
| `Tutorial` | In-app quick guidance for the normal generate/import workflow. |

The shape dump tooling is for research. Full handmade multi-shape import is not currently a finished user feature.

## 11. Prepare FH6 For Import

1. Start Forza Horizon 6.
2. Open `Create Vinyl Group` or `Vinyl Group Editor`.
3. Load or create a template with enough simple layers.
4. Ungroup the template.
5. Keep the editor open.
6. Do not switch menus during import.
7. Remember the exact layer count shown by the game.

The app writes into the currently editable layer table. If the editor state changes, refresh and import again.

## 12. Import JSON Into FH6

1. Open the app's `Import` tab.
2. Click refresh and select the FH6 process.
3. Choose a generated JSON from the browser or manual picker.
4. Enter the exact template layer count.
5. Leave advanced memory fields blank unless you are debugging.
6. Click `Import JSON`.

The app verifies the FH6 template before writing. If verification fails, it stops before import.

## 13. FH6 Boundary Layers

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

If a 2000-layer template is used, the app can write 1996 drawable shapes plus 4 FH6 boundary layers.

## 14. Troubleshooting

### App does not open

Run these in order:

```text
01_add_python312_to_path.bat
02_install_dependencies.bat
05_check_environment.bat
```

### Dependencies keep asking to install

Python is probably not on PATH, or a different Python version is being used. Run `01_add_python312_to_path.bat`, close the command window, then run `02_install_dependencies.bat` again.

### Preview unavailable

Install dependencies again. If preview still fails, generation and import may still work.

### GPU or OpenCL error

Update the NVIDIA, AMD, or Intel GPU driver. The generator uses OpenCL.

### Import says ungroup error

Check:

- You are in Vinyl Group Editor.
- The template is ungrouped.
- The exact template layer count is entered.
- You did not switch menus after preparing the template.
- You selected the correct FH6 process.

### Import permission error

Close the app and run `04_start_app.bat` as administrator.

### Output is too blurry

Use a higher preset, more output layers, more random samples, and a template with enough usable layers.

### Output has edge halos

Keep `Targeted repair` on. Try `Luma Bands` on for flat art, or off for soft sources.

### Import clips the image

The template is too small. Use a larger template or generate fewer output layers.
