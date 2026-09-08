# Local Background Remover

## Scope and Current State

2026-09-08: implemented and hardened in DIRTY only. No version bump,
promotion or publication. Tools' external background-removal link now opens a
native local page following the upscaler. No changes to generation, games, CLEAN
or Native Updated Local. Pre-existing DIRTY work was preserved.

Milestones: verified optional runtime/model installation; isolated cancellable
processing; native page integration; real workflow and failure-path validation.
Stop when these are verified and remaining quality/platform limits are recorded.

## User Workflow

1. Restart DIRTY and open Tools > Open Background Remover.
2. Open an image, drop a local image into the preview, or choose Current source.
3. Choose a mode: Anime (soft edges) is the default for character art; Illustration
   (refined) can clear uncertain patterned-background gaps; Logo / flat colour
   removes a chosen background colour while keeping disconnected lettering.
4. Select Remove background (Download & remove on first AI use). The optional
   model/runtime download is about 187 MiB from GitHub and PyPI. Logo mode needs
   no model, optional runtime or network. Images are never uploaded.
5. Compare, inspect Result/Original/Mask, zoom and pan. Use the erase brush,
   restore-original brush or connected-colour eraser for remaining corrections.
   Every completed edit is saved privately and supports undo/redo.
6. Use as source publishes the current correction and opens Create; Save PNG
   saves a verified copy to a chosen location. Open folder shows the last
   published output. Resume last reopens the saved session after an app restart.
7. Existing transparency is preserved by default, with no model/download needed.
   To change it, enable Advanced > Refine existing transparency. Optional small
   island cleanup stays off by default; four CPU threads are recommended.

Results are new PNGs at the oriented input dimensions. Originals are never changed.
Anime/illustration processing preserves RGB. Logo edge-fringe removal may unmix
the background colour only where this operation reduces alpha; interior colours
remain unchanged. Restore uses the original pixels, never pixels hidden by the
original alpha. There is no
automatic generation or game import. Run report opens the exact job's directory;
Report a problem includes the current error/status, not artwork, using the
existing Other support category. No reporting-server change was necessary.

## Runtime and Limits

- Windows x64, KFPS's CPython 3.12 runtime; no GPU requirement. The child explicitly
  includes the VC++ runtime DLL directory already shipped with PySide6.
- Single image/job, 64 MiB input file and 16-megapixel decoded-image limit.
  Animated and fully transparent inputs are rejected clearly.
- Network reads time out after five seconds; each asset download has a ten-minute
  overall bound. Native processing has a three-minute bound and a sampled 2 GiB
  worker-process-tree RSS limit (a safety bound, not a preallocation guarantee).
  This also covers Windows virtual-environment Python redirectors. Cancel interrupts
  preparation/download or terminates and reaps the worker. App shutdown does too;
  the existing Windows kill-on-close job protects against an orphaned child.
- Engine archives and installed contents are reverified on use. Cached verified
  archives can repair missing/corrupt runtime files without internet. A missing
  model without internet is an explicit failure, never a fake successful cutout.
- Windows sharing/access errors on cache replacement receive eight bounded attempts
  (1.4 seconds total backoff). Cancellation between directory swaps restores the
  previous cache. A failed rollback retains the old cache instead of deleting it.
- A forcibly terminated app can leave an incomplete report/staging file; it is
  never accepted as a completed result. A new attempt is independent, not a resume
  of partially inferred image data. Permanent filesystem locks still require the
  user to resolve the lock/permissions and retry.
- AI inference uses 1024x1024 internally; optional illustration refinement uses
  at most 1400px on its longer edge. Masks return to the original dimensions.
  Refined mode is subtractive and can remove fine details. It is not a universal
  photo segmentation model. Fine hair, translucent effects and complex backgrounds
  still need inspection. Almost-empty results show a prominent review warning.
- Logo mode estimates the dominant edge colour; the pipette overrides it. Tolerance,
  enclosed-background removal and edge-fringe removal are adjustable. Foreground
  using exactly the same colour as the background is inherently ambiguous; use
  edge-only removal or restore it manually. Cleanup is disabled in logo mode.
- Optional small-island cleanup now uses confident component cores and their soft
  edges, rather than letting almost-invisible bridges keep noise connected. It
  remains off by default because small intentional accessories can be removed.
- Corrections run on a background thread at original resolution. Display previews
  are capped at 2400px, zoom at 12x, strokes at 4096 points and brush diameter at
  1000 original pixels (UI slider to 400). Undo during an active stroke is disabled;
  leaving the image ends that stroke instead of joining it across the background.
- Session revisions are verified full-resolution PNGs with an atomic index. At
  most 33 revisions (base plus 32) are kept, with a 128 MiB compressed-revision
  budget; base and current are retained even if those two exceed that budget.
  Preview PNGs are additional. Old revisions and their previews are pruned.
  Completed sessions and original snapshots are private local data, retained
  under runtime for recovery, not automatically uploaded with support reports.
  Removing that runtime session also removes its undo history, not exported PNGs.

## Decisions and Provenance

- ISNet Anime from SkyTNT/anime-segmentation, Apache-2.0. The exact ONNX model
  distributed by rembg is pinned in `tools/background_remover/engine.json`.
  https://github.com/SkyTNT/anime-segmentation
  https://github.com/danielgatis/rembg
- ONNX Runtime CPU 1.22.1, Windows x64 CPython 3.12. Optional wheels are pinned
  by byte size and SHA-256, extracted to a separate private runtime, never pip
  installed into KFPS or the system. Package license files remain in the wheels
  and installed `.dist-info` directories. NumPy and Pillow use KFPS's existing
  dependencies. No PyTorch, Node, GPU or Squeegee installation is required.
  https://onnxruntime.ai/docs/get-started/with-python.html
- ForzaSqueegee established the useful model choice and preprocessing reference.
  No Squeegee source is vendored. Its aggressive component/hull cleanup is not
  copied: separated lettering and accessories must not be removed by default.
  https://github.com/duchil6063/ForzaSqueegee
- Competing approach: use rembg itself with multiple models. Rejected for this
  first tool because its larger dependency/option surface is unnecessary for an
  anime-focused local cutout tool. Universal photo/text segmentation is not claimed.
- Preserve existing alpha by default. Explicit refinement may reduce alpha but
  never reveal previously hidden pixels. Optional island cleanup defaults off.
- OpenCV GrabCut is used from KFPS's existing dependency, not copied source.
  https://docs.opencv.org/4.x/d8/d83/tutorial_py_grabcut.html
- Lucide tool icons are pinned to revision a537cb6eb323b885f4c60baf3cec1a995982d167;
  ISC / Feather MIT license and provenance are in the icon asset directory.
- BiRefNet tiny was trialled and rejected: it removed part of the supplied
  character's tail and exceeded 5 GiB RSS. No additional model is distributed.

## Artifact Locations

- Source: `KFPS.UI/src/kfps_ui/background_remove_*.py` and the QML page.
- Model, verified wheels and optional runtime: `runtime/background-remover/engines`.
- Reports/logs: `runtime/background-remover/runs/<timestamp-id>`.
- Corrections: the same run's `source.png`, `edit-state.json` and `edits/`.
- Last-session pointer: `runtime/background-remover/last-session.json`.
- Correction/resume/save errors: `runtime/background-remover/errors`.
- Results: `Images/Background Removed`; input is never overwritten.
- Local validation evidence: `runtime/background-remover/validation`.

Run folders contain private source snapshots and corrections. Share the report
JSON/logs when diagnosing a failure, not the entire run folder unless sharing the
artwork is intentional. Automatic support context does not attach these PNGs.

## Current Hardening Verification (2026-09-08)

717 regression tests, 54 focused tests with the release Pillow version, two
27-check real UI passes, offline cache repair/recovery and repeated 16MP edits
passed. UI tests cover both supplied failure cases, corrections, restart,
all eight themes and cancellation. The detailed report, exact evidence paths,
performance measurements, rejected experiment and limitations are in
[Background Remover Hardening](BACKGROUND_REMOVER_HARDENING.md).

Status: locally verified and ready in DIRTY. No publication or promotion performed.

## Validation and Lookbacks

M1-M3 checkpoint: isolated dependency/model download verified from upstream;
CPU worker, native page, routing, support context, shutdown and result actions
implemented. First real offscreen KFPS workflow passed 22 checks, including
two actual 1024px cutouts (4.53 and 3.96 seconds end-to-end, 1.25/1.30 seconds
model/session time), existing transparency and text preservation, save/use-result,
all eight themes at 960x600 and 1600x1100, cancellation, retry and app shutdown.
Evidence: `runtime/background-remover/validation/workflow-20260907-223402`.

Lookback after the implementation milestone:
1. Still replacing the external background-removal shortcut, not changing generation.
2. Existing upscaler lifecycle/UI and published ISNet preprocessing were reused as
   patterns. A general rembg installation remains unnecessary.
3. Initial unit failure was a Windows ZIP test assumption: the writer normalizes
   backslashes. Original/normalized archive names are now checked explicitly.
4. Product output, colors/alpha and saved-file reopening are tested, not just speed.
   Simple composited backgrounds remain a quality-test limitation.
5. Complexity is bounded to one model and one worker. No new generic job framework.
6. No generator experiments or previously rejected cleanup heuristic were resumed.
7. Full-job latency is about four seconds, not the earlier 1.2-second model-only
   measurement; verification/startup/PNG encoding account for the difference.
8. More general photo/text models are a possible future alternative, not bundled now.
9. Continue with regression/failure tests and UI fixes; no model-tuning branch.

Visual inspection caught the new page being highlighted as Create in the sidebar.
The Tools route grouping was corrected. Worker output is accepted only after
format/dimension, unchanged-RGB, subtractive-alpha and reopened-PNG validation.

## Original Implementation Verification (2026-09-07)

- 695 regression tests passed in 50.217 seconds, including 32 focused remover
  tests. Evidence: `runtime/background-remover/validation/2026-09-07/full-regression-verified.txt`
  and `unit-tests-final.txt`. The earlier failed full run is retained as
  `full-regression-final.txt`; its transient Windows cache-rename error prompted
  the retry/rollback tests and fix, not a suppressed assertion.
- Actual offscreen KFPS UI: 22 checks passed, no QML errors, all eight themes at
  960x600 and 1600x1100. Includes real model processing, native Tools routing,
  comparison, source selection, copy save, source-overwrite protection, CPU combo,
  tab switching, cancellation/retry and shutdown with a real worker active.
  Evidence: `runtime/background-remover/validation/workflow-20260907-225053/results.json`
  and its screenshots. No visible windows or desktop focus were taken.
- Final real-engine resilience pass: nine successful CPU jobs plus a deliberate
  offline/missing-model failure and recovery; missing native binary and corrupt
  module rebuilt offline, restart/new store, Unicode paths, repeated identical
  output hashes, optional refinement/cleanup and source preservation all passed.
  Evidence: `runtime/background-remover/validation/resilience-20260907-230741/results.json`.
- Warm 1002x1024 runs: about 4.0-4.3 seconds total; model/session about 1.2-1.3
  seconds. Cold preparation and repair runs were around 15-17 seconds. Per-phase
  timings distinguish preparation from inference instead of suggesting the whole
  job takes only the model's inference time.
- On this fixture the worker peaked around 718-776 MiB across runs, then exited.
  The standalone harness's parent RSS stabilized around 58 MiB during repeats.
  No CPU worker survived completion, cancellation, or normal app shutdown. This
  is a bounded local observation, not proof against every possible memory leak.
- Mascot foreground IoU was 0.9932 on white and 0.9892 on blue-grey; average alpha
  error was 1.42/1.85 on a 0-255 scale. These are two simple composites of one
  known transparent character, not a broad natural-background quality benchmark.
- The full suite still emits a PySide/Python shutdown garbage-collection warning
  (184 objects). A previous upscaler baseline also emits this class of warning
  (178). It was not hidden or classified as proof of a model-memory leak; the
  real-worker lifecycle/resource checks above are the relevant new evidence.
- Release-dependency compatibility also passed: an isolated test environment with
  Pillow 12.3.0 ran all 32 remover tests and the full 22-check real KFPS UI workflow.
  The two foreground/alpha comparison scores were identical to Pillow 11.3.0.
  Evidence: `runtime/background-remover/validation/2026-09-07/pillow-12.3-unit-tests.txt`
  and `runtime/background-remover/validation/workflow-20260907-231749/results.json`.
  Pillow's pinned PyPI wheel SHA-256 was
  `a2b55dd6b2a4c4b7d87ffa56bdb33fdc5fdb9a462173861a7bc097f17d91cb09`.
  The host/app Python environment was not modified by this compatibility test.
- Other Windows versions, CPUs and fresh-machine installation configurations have
  not been tested here. Validation used Python 3.12.10, NumPy 1.26.4, Pillow 11.3.0
  and 12.3.0, and PySide6 6.11.1. This is local validation, not a hardware matrix.

Original implementation lookback: the discovered failure was filesystem replacement under transient
Windows locks, not model quality or dependency mismatch. Bounded retries follow
the application's existing atomic-write pattern; permanent failures still stop.
No additional model, generator branch, generic job framework or deployment was
added. The requested local workflow now works, outputs reopen correctly, source
images remain unchanged, dependencies are isolated, and limitations are explicit.
Source/docs live in their named repository locations; all downloads and test
artwork remain beneath ignored runtime directories. The later supplied images
disproved the original assumption that the one-model workflow was sufficient;
the hardening decisions and current evidence are in BACKGROUND_REMOVER_HARDENING.md.

## Repeat the Checks

Use KFPS's Python 3.12 runtime from the DIRTY root:

```text
python -B -m unittest discover -s KFPS.UI/tests -p "test_background_remove*.py" -v
python -B KFPS.UI/tools/test_background_remover_workflow.py
python -B KFPS.UI/tools/test_background_remover_resilience.py
python -B KFPS.UI/tools/test_background_remover_edit_stress.py
python -B -m unittest discover -s KFPS.UI/tests -v
```

The UI harness uses an isolated app/settings directory under runtime and stays
offscreen. Optional KFPS_BG_TEST_LOGO and KFPS_BG_TEST_CHARACTER environment
variables add the supplied real-image cases without checking private images into
source control. The resilience harness makes a disposable copy of this feature's
cache, tests corruption/offline repair there, and removes only that test copy.
The edit-stress harness exercises the service at 16MP and reopens its history in
a separate process. All evidence goes under ignored runtime. None access a game
or save, take desktop focus, or modify original inputs.
