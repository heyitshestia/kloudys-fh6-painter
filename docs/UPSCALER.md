# Native Upscaler

## Scope and checkpoints

Implementation and initial validation were completed in KFPS DIRTY. On
2026-09-07, Hestia approved promotion to CLEAN/main and a 3.1.62 bundled release.
Existing support-reporting changes are preserved. Native Updated Local is untouched.

1. Integration: local Tools > Upscaler, Photo/Anime/Text presets, 2x/4x,
   collapsed advanced controls, previews, cancel, save and use-as-source.
2. Runtime: pinned upstream native engines, verified first-use downloads,
   bounded image sizes, isolated processing, durable diagnostics, no uploads.
3. Validation: real native processing, alpha edges, exact dimensions, cancellation,
   repeated jobs, failure recovery, QML interaction and regression suite.

Success requires reopening generated PNGs and exercising the actual service/UI.
Stop and reconsider if transparent inputs lose their alpha, tiling produces
visible seams, or repeated runs retain native processes.

## Design decision

Use Real-ESRGAN NCNN Vulkan for photos and waifu2x NCNN Vulkan for anime/text.
Native helpers avoid the browser compatibility and model conversion work of
ONNX WebGPU. Using two existing CLIs avoids inventing a general model host.
The model runtimes are lazy and do not load while navigating unrelated pages.

Code licenses: both helper projects are MIT; Real-ESRGAN model provenance is
the upstream Real-ESRGAN release (BSD-3-Clause project), and waifu2x models are
from the upstream waifu2x NCNN release. Preserve all upstream notices. Do not
silently substitute arbitrary third-party models or download floating latest URLs.

- https://github.com/xinntao/Real-ESRGAN
- https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan
- https://github.com/nihui/waifu2x-ncnn-vulkan
- https://github.com/nagadomi/waifu2x

## Artifact locations

- Engine catalog/notices: `tools/upscaler/` (tracked).
- Python integration: `KFPS.UI/src/kfps_ui/upscale_*.py` (tracked).
- Engine downloads and installed files: `runtime/upscaler/engines/` (local).
- Per-run manifests, native log and intermediate images: `runtime/upscaler/runs/`.
- Completed images: `Images/Upscaled/` (local, never overwrite the original).
- Validation evidence: `runtime/upscaler-testing/` (local).

## Current status: ready for DIRTY testing, 2026-09-06

All three implementation checkpoints are complete locally. Tools > Open Upscaler
now opens the retained native page. It offers image selection/drop, current source,
2x/4x, before/after comparison, cancellation, Save as, Open folder, Use as source,
and per-run diagnostics. Advanced noise/tile/GPU/TTA controls start collapsed.
Changing a preset or pressing Reset restores its recommendations.

The first use downloads only the selected engine (approximately 43 MB for
Real-ESRGAN, 34 MB for waifu2x). This is not a new Python, CUDA, Node.js, or browser
dependency. It requires 64-bit Windows and a Vulkan-capable GPU/driver. Once the
engine is installed, subsequent jobs can run without network access. Both model
directories are verified before use and repaired through a pinned download if
their files are missing or damaged. Original source files are never changed.

Photo uses an intrinsically 4x model; requested 2x is downsampled after inference.
Text is an image upscaling preset, not OCR or font reconstruction. Model-invented
details and excessive denoising remain possible; compare the result before use.
Transparent images retain their alpha, resampled separately from model RGB.

### Bounds and lifecycle

- Single job at a time; a second click cannot queue overlapping jobs.
- Input limit: 64 MB and 16 million pixels.
- Native processing limit: 32 million pixels. Photo 2x also incurs native 4x.
- Tiles default to 128px, processing threads to 1:1:1; TTA defaults off.
- Native processing timeout: 15 minutes; download time budget: 5 minutes.
- Native helpers have hidden windows and Windows kill-on-close job ownership.
- Cancel or application close stops and reaps the active native helper.
- Completed PNGs are reopened and dimension-checked before atomic publication.
- A final report or preview write failure does not hide a successfully saved PNG.
- Inputs/native intermediates are removed after a job. Final outputs and run
  diagnostics/previews remain on disk; there is no automatic retention expiry.
- Service state is retained across tab changes, not restored after app restart.
  Previously completed files and diagnostic reports remain available on disk.

### Evidence

Authoritative real-workflow run:
`runtime/upscaler-testing/workflow-20260906-203418/results.json`.
The folder contains original fixtures, six reopened outputs, manifests/native logs,
six before/after screen captures, 16 theme/window captures, and a splash capture.
These are ignored local validation artifacts, not release assets.

The real workflow used the actual app shell, service, native executables and
QML button clicks. File-dialog choices were supplied by the harness. Qt rendered
offscreen without moving focus. Native inference used the NVIDIA RTX 4090.

| Preset | Input | 2x seconds | 4x seconds |
| --- | --- | ---: | ---: |
| Photo | 512x480 photograph | 3.339 | 3.485 |
| Anime | 251x256 transparent illustration | 1.072 | 1.062 |
| Text | 320x180 transparent lettering | 0.796 | 0.817 |

Times include local verification and output work, with engines already installed.
They are fixture measurements on this GPU, not broad performance guarantees.
An earlier full-size 1241x1268 anime 2x run also completed; its evidence is in
`runtime/upscaler-testing/native-first/` (before the alpha resampling refinement).

Checks passed: six preset/scale combinations, alpha and output dimensions,
double-start protection, settings locked during work, Save as byte equality,
Use as source, tab navigation, preset reset, active GPU cancellation followed by
a successful job, eight themes at 960x600 and 1600x1100, and no QML errors.
No NCNN native processes remained after the workflow exited.

Focused tests also cover animated/malformed/oversized inputs, EXIF orientation,
palette transparency, invalid settings, wrong native dimensions, nonzero exit,
timeout, helper termination on job close, damaged/missing files, truncated or
incorrect downloads, missing archive members, concurrent installers, cancellation,
interrupted installation/repair, report failure and preview failure.
All 653 regression tests passed in 50.526 seconds, including 27 focused upscaler
tests. The regression log is `runtime/upscaler-testing/full-tests-final.log`.
It still prints the suite's existing shutdown ResourceWarning; this result is
not a claim that unrelated QObject lifetime warnings have been eliminated.
A Command Prompt theme corner regression was caught and fixed with the existing
Theme.corner helper before the successful full-suite rerun.

Photo fixture provenance: OpenCV 4.10.0
`samples/data/fruits.jpg`, downloaded by the opt-in harness with its SHA-256
pinned. Used only for local validation, never vendored or included in bundles.
https://github.com/opencv/opencv/blob/4.10.0/samples/data/fruits.jpg

### Reproduce

From the KFPS root, using its configured Python environment:

```powershell
python -m unittest discover -s KFPS.UI/tests -p test_upscaler.py -v
python KFPS.UI/tools/test_upscaler_workflow.py
python -m unittest discover -s KFPS.UI/tests
```

The real-workflow script is deliberately opt-in: it can download pinned engines
and the small photo fixture and use the GPU. It isolates settings and generated
outputs beneath `runtime/upscaler-testing/`. No live game is involved.

### Remaining validation limits

- AMD, Intel, older Windows versions and multi-GPU selection need other machines.
- No forced reboot/power-loss test or adversarial antivirus/OneDrive lock matrix.
- Vulkan-unavailable failures are surfaced, not replaced by a silent CPU model.
- No proof of universal perceptual quality, exact missing-text recovery, or exact
  color matching for unusual embedded color profiles.
- This task does not build a release bundle or validate a new public update.

## Lookbacks and decisions

1. Scope remains a local upscaler plus the requested splash replacement. No
   generator, live-memory, community backend, or updater behavior was changed.
2. Reused existing source service, lazy pages, themes, reporting context and
   installed OpenCV. Removed an initial SciPy requirement because it was absent
   and added no value over the existing OpenCV distance transform.
3. The alpha-edge issue was resampling, not the model: Lanczos alpha introduced
   ringing in thin opaque strokes. Bilinear alpha passed the targeted tests.
4. Validation covers actual button-driven saved files and visual output, not
   only mocks. Corrected the purported photo fixture after inspection showed
   the engine archive's input.jpg was an illustration; reran with a real photo.
5. Kept two small CLI adapters instead of adding a general model-host framework.
   New functionality and failure tests justify the added code without another
   resident inference service.
6. No repeated model tuning or per-image exceptions were introduced. Presets use
   upstream models and the same alpha handling for every image.
7. Raw image inspection can display hidden RGB in transparent pixels. Alpha
   values and the actual Qt checkerboard preview confirmed those pixels remain
   invisible; no unnecessary model/alpha change was made for that display artifact.
8. Browser ONNX/WebGPU remains the main alternative, but brings browser/device
   and conversion dependencies. A complete external upscaler app would add more
   UI/runtime surface than this scoped integration needs.
9. Continue with user testing in DIRTY; stop architecture work here. Do not claim
   cross-vendor validation until those hardware runs exist.

## Splash artwork

Replaced `KFPS.UI/assets/mini-kloudy.png` with the exact supplied transparent PNG.
SHA-256: `763f8eae1613dccc11289ce5857656e3f664915548055da9a3bd0c024dbf653e`.
It is RGBA, 1241x1268; approximately 50.8% of pixels are fully transparent and
all four corners have alpha zero. Most visible pixels are nearly opaque rather
than alpha 255; this original translucency was preserved, not edited away.
The artwork now fits the existing 220px-high label without cropping. Circular
layout, title, colors and animated split rings are unchanged. See `splash.png`
in the authoritative workflow folder.
