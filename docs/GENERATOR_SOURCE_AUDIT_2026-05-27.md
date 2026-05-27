# Generator Source Audit - 2026-05-27

Scope:
- App wrapper and preset pipeline: `generator_backend.py`, `settings/*.ini`
- Python V2/finalization layer: `forza_generator_v2.py`
- Go/OpenCL raw generator source: `/home/hestia/Desktop/FH6_Patched_Generator_Windows_Build/generator-v5-prototype`
- Current shipped app generator: `KloudysGeneratorV5.exe`

Current active app version at audit time: `1.10.30`

Current active app commit at audit time: `4a564dc`

## Executive Summary

The active generator pipeline is functional, but there are several discrepancies worth fixing before more generator tuning:

1. The V2 finalizer still reserves 4 FH boundary layers even though legacy border masks are disabled by default in the app. That silently lowers usable generated detail.
2. Canvas-boundary penalties are added to shape contribution scores during pruning, when they should reduce net contribution. This can make bad overhanging shapes harder to prune.
3. The raw Go preview renderer ignores per-shape alpha and renders every shape as fully opaque, so live/raw previews can disagree with final gradient behavior.
4. The active shipped executable matches the Windows generator source folder, but not the stale Linux-side exe copies. The source files match between Linux and Windows, but local Linux binaries in the prototype folder are stale.
5. Go tests/builds are not currently reproducible from a plain command because OpenCL headers are not in the default compiler include path. The build script knows about the bundled SDK, but `go test ./...` does not.

## Pipeline Summary

The app does not call the Go generator directly. The flow is:

1. `generator_backend.py` builds a Python command for `forza_generator_v2.py`.
2. `forza_generator_v2.py` optionally creates a Luma Prep image.
3. `forza_generator_v2.py` writes a temporary `.v2.settings.ini`.
4. `forza_generator_v2.py` runs `KloudysGeneratorV5.exe`.
5. The Go generator writes internal checkpoints into `imgs/generated/<run>/checkpoints`.
6. Python V2 finalization scores, repairs, prunes, renders previews, and writes import-ready JSONs into `imgs/generated/<run>/finals`.

Important consequence: raw checkpoint JSONs are not final import targets. The final JSON browser should use `finals/*v2.json`.

## Confirmed Bugs

### 1. V2 still reserves 4 boundary layers even when masks are off by default

Severity: High for quality/detail budget.

File: `forza_generator_v2.py`

Relevant lines:
- `FH6_RESERVED_BOUNDARY_LAYERS = 4` at line 27.
- `drawable_target_shapes = max(1, target_shapes - FH6_RESERVED_BOUNDARY_LAYERS)` at line 1943.
- Log message still says `target - 4 FH bounds layers` at line 1971.

Why this is wrong now:
- The app importer defaults legacy border masks off.
- `app_qt.py` only reserves mask layers when `legacy_border_masks` is enabled.
- The generator finalizer has no awareness of that setting and always caps final drawable count at `target_shapes - 4`.

Observed effect:
- A `2000` layer target finalizes to at most `1996` drawable shapes even when the importer will not add the 4 big FH border masks.
- This wastes shape budget on every normal generation and can reduce detail.

Recommended fix:
- Add an explicit V2 argument such as `--reserved-import-layers`.
- Default it to `0`.
- Pass `4` only when legacy border masks are enabled.
- Update the log text to say exactly how many reserved layers are active.

### 2. Boundary penalty has the wrong sign in pruning contribution scoring

Severity: High for edge adherence and post-process pruning correctness.

File: `forza_generator_v2.py`

Relevant lines:
- `contrib_map = diff_under - diff_top` at line 904.
- Boundary penalties are computed at line 914.
- `contributions += boundary_penalties` at line 916.
- Total error correctly adds penalties at line 918.

Why this is wrong:
- `contrib_map` means "how much this top shape improves the image."
- Higher contribution means "keep this shape."
- Boundary penalty means "this shape is making the image worse by violating the canvas."
- Therefore a boundary penalty should lower that shape's net contribution, not raise it.

Expected logic:

```python
contributions -= boundary_penalties
```

Observed effect:
- A shape with bad overhang can be treated as more valuable during pruning.
- This works against the edge repair/canvas-boundary intent.

Recommended fix:
- Change `contributions += boundary_penalties` to `contributions -= boundary_penalties`.
- Add a small regression test with one useful shape and one overhanging harmful shape to prove pruning removes the harmful one first.

### 3. Raw Go preview ignores per-shape alpha

Severity: Medium/high for gradient preset trust and live-preview accuracy.

File: `internal/render/ellipse.go`

Relevant lines:
- `c := color.RGBA{..., A: 255}` at line 98.
- `previewCandidateFromShape()` uses that fully opaque alpha at line 133 onward.

Why this is wrong:
- The Go generator can emit alpha below 255 when `forceOpaqueShapes=false`.
- The Smooth Gradients preset uses `forceOpaqueShapes=false`.
- JSON output preserves alpha, but raw preview snapshots render every shape opaque.

Observed effect:
- Live/raw previews can look blockier or harsher than the actual final JSON.
- Users can misjudge gradient preset quality while generation is running.

Recommended fix:
- Use `A: uint8(s.Color[3])` instead of `A: 255`.
- Ensure `fillRect`, `applyRotatedRectSolid`, and `applyEllipseSolid` actually alpha-composite rather than overwrite.
- If those render helpers are intentionally solid-only, add alpha-aware preview helpers.

### 4. Raw preview cleanup can race with UI polling

Severity: Medium.

File: `forza_generator_v2.py`

Relevant lines:
- Snapshot cleanup/promote logic at lines 1796-1821.
- Cleanup runs when the generator prints `Saved preview snapshot`, line 1830 area.

Risk:
- The finalizer copies the newest numbered raw preview to a stable path and deletes the numbered snapshots.
- If the UI polls the stable preview while it is being replaced, image loading can see transient missing/incomplete files.

Current mitigation:
- Replacement uses a temporary file and `os.replace`, which is mostly safe.

Remaining risk:
- The generator itself may still write numbered preview PNGs while cleanup is scanning/copying.
- This likely explains past intermittent "PNG input buffer is incomplete" style preview errors if the cleanup copies a file before the generator fully finishes writing it.

Recommended fix:
- Only promote snapshots whose mtime is older than a small settle window, for example `>= 100-200 ms`.
- Alternatively have the raw generator write preview snapshots to a temp file and atomically rename them.

## Source And Build Discrepancies

### 5. Active executable source-of-truth is split between Linux and Windows folders

Severity: Medium.

Findings:
- Active app exe hash:
  - `KloudysGeneratorV5.exe`
  - SHA256: `37186882f3baa9febc39de16e47ea7b2f85b245a911ccbb59cbc20db26685b7e`
- Windows source folder binaries match that hash:
  - `C:\Users\Hestia\Desktop\FH6_Patched_Generator_Windows_Build\generator-v5-prototype\kloudys-fh6-generator.exe`
  - `C:\Users\Hestia\Desktop\FH6_Patched_Generator_Windows_Build\generator-v5-prototype\forza-painter-geometrize-go.exe`
- Linux source folder binaries do not match that hash:
  - `/home/hestia/Desktop/FH6_Patched_Generator_Windows_Build/generator-v5-prototype/kloudys-fh6-generator.exe`
  - SHA256: `5f048d183a1e0cabb373bcc336a6177856c9de04d7df350e6aba95cb7a4e5de2`

Important nuance:
- The checked source files sampled on Linux and Windows match by SHA256.
- The stale part is the Linux-side generated executable copies, not the source text.

Recommended fix:
- Treat `generator-v5-prototype` source as canonical.
- Add a build output verification step that writes `KloudysGeneratorV5.exe.sha256`.
- Copy the current Windows-built exe back to the Linux prototype folder after every accepted build, or stop storing generated exe files in prototype folders entirely.

### 6. Top-level build script still builds `patched-generator`, not `generator-v5-prototype`

Severity: Medium.

File: `/home/hestia/Desktop/FH6_Patched_Generator_Windows_Build/BUILD_PATCHED_GENERATOR.bat`

Relevant lines:
- `set "SRC=%ROOT%patched-generator"`

Why this matters:
- `patched-generator` and `generator-v5-prototype` differ in core files:
  - `internal/config/settings.go`
  - `internal/engine/engine.go`
  - `internal/gpu/kernels.go`
  - `internal/gpu/opencl.go`
  - `internal/imageutil/image.go`
  - `internal/model/types.go`
- `generator-v5-prototype` contains the V5 detail-weighting code.
- Running the top-level build script can produce a generator that is not the current V5 behavior.

Recommended fix:
- Rename the top-level script to make its target explicit.
- Add a `BUILD_KLOUDYS_GENERATOR_V5.bat` that builds `generator-v5-prototype`.
- If `patched-generator` is retained as an archive, label it as archive/legacy.

### 7. `go test ./...` does not work without OpenCL include environment

Severity: Medium for maintainability.

Observed Windows result:

```text
fatal error: CL/cl.h: No such file or directory
FAIL forza-painter-geometrize-go/internal/gpu [build failed]
```

Why this matters:
- The bundled `build-opencl.ps1` sets `CGO_CFLAGS` and `CGO_LDFLAGS`.
- Plain `go test ./...` does not.
- That makes a normal source audit/build verification fail even though the build script can compile.

Recommended fix:
- Add `test-opencl.ps1` that sets the same environment as `build-opencl.ps1` and then runs `go test ./...`.
- Add that test script to the release/build checklist.

## Behavior That Is Intentional But Easy To Misread

### 8. Non-alpha images do not enforce canvas edge boundaries

File: `forza_generator_v2.py`

Relevant lines:
- `target_has_alpha_boundary()` at lines 527-531.
- Boundary mode selected at lines 2012-2021.

Current behavior:
- If the source image has transparency, transparent outer edge spans are constrained.
- If the source has no alpha transparency, outer PNG edges are unconstrained.

Why it exists:
- A fully opaque source may be intended to cover the entire canvas, so the edge is not automatically treated as a cutout boundary.

User-facing implication:
- If someone wants strict border adherence around a logo, the source should have a transparent border/background.

Recommendation:
- Document this clearly in the UI and manual.
- Consider an advanced toggle: `Treat canvas edge as hard boundary`.

### 9. Active presets omit several V5 raw generator controls

Files:
- `settings/a.flat-colors.ini`
- `settings/b.shaded-art.ini`
- `settings/c.gradients.ini`

Raw V5 supports:
- `detailWeighting`
- `fastPrefilter`
- `prefilterScale`
- `prefilterKeepRatio`
- `prefilterMinKeep`
- `detailMode`

Current presets:
- Do not explicitly set most of those.
- Therefore V5 defaults apply.

This is not necessarily wrong. It is a discrepancy between what the raw generator supports and what the user-facing presets expose.

Recommendation:
- Either intentionally expose these in custom settings documentation or explicitly lock them in each preset for reproducibility.

### 10. `saveEvery` and `previewEvery` are overwritten for live previews

Files:
- `generator_backend.py`
- `forza_generator_v2.py`

Relevant lines:
- App hardcodes `live_preview_every = 50` in command metadata and args at `generator_backend.py` lines 511 and 533-534.
- V2 writes both `saveEvery` and `previewEvery` to this value at `forza_generator_v2.py` lines 250-260.

Why this matters:
- Presets contain `saveEvery = 250`.
- The raw generator receives `saveEvery = 50` for live preview behavior.
- JSON checkpoint creation is still controlled by `saveAt`, so this mostly affects preview cadence.

Recommendation:
- Rename this concept in metadata/UI to `livePreviewEvery`.
- Avoid making preset `saveEvery` look like the active runtime value unless it actually is.

### 11. Shape-mode schedules intentionally reduce rectangles late

File: `internal/engine/engine.go`

Relevant lines:
- `mixed_soft_detail` at lines 1900-1929.
- `mixed_character_art` at lines 1930-1964.
- `mixed_smart_detail` at lines 1965-1999.

Current behavior:
- Smooth/detail presets heavily reduce or eliminate rectangles late in generation.
- `mixed_edge_bias` keeps strong rectangle usage for logo/flat-color work.

This is intentional and matches the current preset design:
- `Flat colors` should use more rectangles.
- `Smooth gradients` should use fewer top-layer rectangles.
- `Shaded art` is between those two.

## Low-Severity Cleanup

### 12. Dead/stale preview path helper

File: `generator_backend.py`

Relevant lines:
- `generator_preview_path()` at lines 350-352.

Issue:
- It returns `previews/<source_stem>.preview.png`.
- Current raw live preview path is `previews/<run_stem>.raw.preview.png`.
- Search indicates this helper is not currently used.

Recommendation:
- Remove it or update it to the current preview contract to avoid future accidental use.

### 13. V2 CLI description still says "ellipse layers"

File: `forza_generator_v2.py`

Relevant lines:
- CLI description around lines 38-44.

Issue:
- The current pipeline supports rectangles and ellipses.
- The wording still says "ellipse layers."

Recommendation:
- Change wording to "drawable layers" or "shape layers."

## Recommended Fix Order

1. Fix V2 reserved layer count to default to `0`, only reserving layers when legacy masks are enabled.
2. Fix boundary penalty contribution sign and add a tiny pruning regression test.
3. Fix raw Go preview alpha rendering.
4. Add a dedicated V5 build/test script and stop using the top-level script for `patched-generator`.
5. Add OpenCL-aware `go test` wrapper.
6. Clean stale helper/docs wording.
7. Decide whether V5 controls should be explicit in presets or remain generator defaults.

## Verification Commands Used

Hash active generator:

```bash
sha256sum /home/hestia/Desktop/KloudysFH6Painter/KloudysGeneratorV5.exe
```

Compare Linux source tree to archived patched source:

```bash
diff -qr \
  /home/hestia/Desktop/FH6_Patched_Generator_Windows_Build/generator-v5-prototype \
  /home/hestia/Desktop/FH6_Patched_Generator_Windows_Build/patched-generator \
  -x '*.exe' -x demo -x OpenCL-SDK -x '*.png' -x '*.jpg'
```

Check Windows Go availability:

```bash
ssh hestia@192.168.0.241 'powershell -NoProfile -Command "go version"'
```

Attempt Windows Go tests:

```bash
ssh hestia@192.168.0.241 'powershell -NoProfile -Command "cd $env:USERPROFILE\Desktop\FH6_Patched_Generator_Windows_Build\generator-v5-prototype; go test ./..."'
```

Result: failed because `CL/cl.h` was not found by plain `go test`.

