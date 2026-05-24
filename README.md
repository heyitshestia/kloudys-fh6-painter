# Kloudy's FH6 Painter

[English](README.md) | [中文](README.zh-CN.md)

Image-to-vinyl generator and FH6 importer for **Forza Horizon 6**.

This project turns an image into Forza vinyl geometry JSON, then imports that JSON into an open FH6 Vinyl Group Editor template.

## Thank You / Credits

This project exists because several people and upstream projects did the hard foundational work first. License notices are kept in [LICENSE](LICENSE) and [LICENSE.geometrize-gpu](LICENSE.geometrize-gpu).

| Person / project | Link | Contribution |
| --- | --- | --- |
| AE / A-Dawg#0001 | https://github.com/forza-painter/forza-painter | Original Forza Painter project, MIT-licensed FH import workflow, memory-writing/import foundation, and core geometry-to-vinyl approach. |
| BVZRays / bvz rays | https://github.com/bvzrays/forza-painter-fh6 | FH6-focused desktop fork used as the main upstream for this project, including FH6 UI workflow, importer/locator work, release packaging, documentation updates, and bundled app behavior. |
| zjl88858 / forza-painter-geometrize-gpu | https://github.com/zjl88858/forza-painter-geometrize-gpu | GPU/OpenCL geometrize generator lineage used by the bundled `forza-painter-geometrize-go.exe`. |
| Sam Twidale | https://samcodes.co.uk/ | `geometrize-lib` author; original geometry approximation work credited by the project license. |
| Michael Fogleman | https://github.com/fogleman/primitive | `primitive` author; original primitive-based image approximation library credited by the project license. |
| Sanguk Ko / ree9622 | https://github.com/ree9622 | Korean localization contributor in the BVZRays upstream history. |
| heyitshestia / Kloudy | https://github.com/heyitshestia/kloudys-fh6-painter | This fork: Luma Bands workflow, V2 checkpoint/finalization changes, targeted repair defaults, checkpoint browser, updater batch, preset/UI changes, theme support, and FH6 import safety adjustments. |

## Read This First

Run the setup files in this order before doing anything else:

1. Install **64-bit Python 3.12** from the official Python website:
   https://www.python.org/downloads/release/python-31210/
2. Double-click:

```text
01_add_python312_to_path.bat
```

3. Double-click:

```text
02_install_dependencies.bat
```

4. Start the app:

```text
04_start_app.bat
```

Do not open the app before installing Python 3.12 and dependencies. If something fails, run:

```text
05_check_environment.bat
```

## Updating

Use only this file to update:

```text
03_update_from_github.bat
```

Close the app first. Do not update by dragging random files over the folder. The updater pulls the latest GitHub files and preserves generated/runtime output. If Git is missing, the updater installs PortableGit for the current Windows user automatically.

## What It Does

- Generates Forza-compatible JSON from PNG, JPG, BMP, and similar image files.
- Uses the bundled GPU/OpenCL generator: `forza-painter-geometrize-go.exe`.
- Adds V2 post-processing for checkpoint handling, pruning, reports, targeted repair, and previews.
- Imports generated JSON into the currently open FH6 vinyl group.
- Scans old generated folders on startup so previous checkpoints can be imported later.

## Quick Workflow

1. Install Python 3.12 and dependencies with the batch files above.
2. Open the app with `04_start_app.bat`.
3. In `Generate JSON`, choose one image.
4. Pick a quality preset or enable custom settings.
5. Leave `Luma Bands` and `Targeted repair` on unless the source looks better without them.
6. Click `Start generating`.
7. Open FH6 and go to `Create Vinyl Group` / `Vinyl Group Editor`.
8. Load a template with enough simple layers and ungroup it.
9. In the app, go to `Import`.
10. Select the generated JSON, enter the exact template layer count, and import.

Full instructions are in [docs/USER_MANUAL.md](docs/USER_MANUAL.md).

## Important Import Rule

FH6 needs **4 boundary layers** for correct cover/apply behavior.

That means the usable drawable count is:

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

If your JSON has more shapes than the usable count, the app trims it during import.

## Active Presets

The app currently shows the simple five-preset ladder:

| Preset | Output layers | Random samples | Mutated samples | Max resolution | Use case |
| --- | ---: | ---: | ---: | ---: | --- |
| Extremely fast | 500 | 30000 | 1000 | 600 | composition tests |
| Fast | 1000 | 60000 | 2000 | 900 | quick drafts |
| Balanced | 1800 | 120000 | 5000 | 1400 | normal default |
| Slow | 2500 | 220000 | 8000 | 2000 | cleaner final output |
| Super slow | 3000 | 350000 | 12000 | 2400 | highest bundled quality |

Custom settings can override the preset for one run without editing `.ini` files.

## Main Features

- **Luma Bands**: default-on preprocess pass. It creates a luma-banded intermediate image before generation. Good for anime, flat colors, and sharper value separation. Turn it off for soft gradients.
- **Targeted repair**: default-on V2 cleanup. It tries to clean border mess, transparent holes, fingers, hair gaps, and cutout edges after raw generation.
- **vroom vroom scrrrrt zoooom!**: optional switch. Doubles effort-style numeric settings such as samples while keeping output layers and resolution unchanged.
- **Checkpoint browser**: shows generated folders and checkpoints from `imgs`, including older runs after restart.
- **Run reports**: every V2 run writes a `*.v2.report.json` with preset, custom settings, effective settings, toggles, candidates, and selected outputs.

## Examples

Source/result examples are included in [docs/examples/test-finest](docs/examples/test-finest):

| Source | Generated result |
| --- | --- |
| <img src="docs/examples/test-finest/miku-original.png" width="360" alt="Miku source"> | <img src="docs/examples/test-finest/miku-vinyl.png" width="360" alt="Miku vinyl result"> |
| <img src="docs/examples/test-finest/pokemon-original.png" width="360" alt="Pokemon source"> | <img src="docs/examples/test-finest/pokemon-vinyl.png" width="360" alt="Pokemon vinyl result"> |

## Limitations

- The generator/importer path is currently ellipse-based.
- Full handmade multi-shape import is not feature-complete yet.
- FH6 import requires Windows, FH6 running, and the correct editor state.
- GPU generation requires working OpenCL support from the GPU driver.
- Importing may require running the app as administrator.

## Common Problems

- **The app will not start**: install Python 3.12, run `01_add_python312_to_path.bat`, then run `02_install_dependencies.bat`.
- **Preview unavailable**: run `02_install_dependencies.bat`; generation/import can still work without preview dependencies.
- **OpenProcess or permission error**: run `04_start_app.bat` as administrator.
- **Game process not found**: start FH6 first, then click refresh in the import tab.
- **Ungroup error even though it is ungrouped**: make sure you are inside Vinyl Group Editor, the layer count is exact, and the active group is the template being edited.
- **Output is blurry**: use more output layers, higher random samples, a higher-resolution preset, or a larger template.
- **Output is clipped**: the template does not have enough usable layers.

## License

This project is a derivative of the Forza Painter workflow and keeps the original MIT license notices in [LICENSE](LICENSE) and [LICENSE.geometrize-gpu](LICENSE.geometrize-gpu).
