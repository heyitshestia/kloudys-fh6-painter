# Background Remover Hardening

## Active Scope

2026-09-08: user authorized a polished, production-ready implementation in DIRTY.
Do not promote to CLEAN, change Native, push, bump or bundle. Preserve the supplied
originals and all pre-existing work. This document is the current-state/checkpoint
record for this task; `BACKGROUND_REMOVER.md` remains the user/implementation guide.

Baseline: `runtime/background-remover/validation/user-cases-2026-09-08`.
Current anime model destroys the F1 logo and leaves background in the character's
tail loop. Existing cleanup does not meaningfully improve either. Almost-empty
results incorrectly appear successful. Four original product runs are frozen.

## Milestones

- M1 COMPLETE: compare one official general-purpose ONNX candidate on the supplied
  cases and existing fixtures. Record provenance, timings, memory and visible
  regressions. Stop model exploration after two non-improving trials.
- M2 COMPLETE: implement explicit anime/refined illustration/flat-colour
  modes, dependable edge handling, quality warnings and conservative cleanup.
  Test disconnected lettering, enclosed background, existing alpha and limits.
- M3 COMPLETE: native correction workflow with zoom, erase/restore and undo/redo;
  retain originals, save verified revisions and diagnose errors. UI must remain
  responsive and work in existing themes and compact layouts.
- M4 COMPLETE: actual user-path tests, interruption/restart/repair, regression
  suite, repeated resource checks and documentation. Stop only with evidence of
  the complete workflow and explicit platform/model limitations.

## Alternatives and Decisions

- Colour-based extraction is appropriate for flat-background logos and does not
  need a learned subject model. Edge-connected flood fill alone cannot remove
  enclosed same-colour holes. Offer explicit control over that distinction.
- A general model is a candidate, not an assumed quality upgrade. Start with
  official BiRefNet tiny ONNX (224,005,088 bytes), not a near-1GB full model.
  Official source: https://github.com/ZhengPeng7/BiRefNet (MIT).
  No upstream executable Python or pickle checkpoint will be loaded.
- User-guided corrections are complementary to segmentation, not a claim that
  any model can determine all intended disconnected foreground automatically.
- Aggressive largest-component filtering remains rejected for logos/accessories.
- Keep one product implementation. All experiments are under ignored runtime;
  no extra clones/worktrees or runtime copies in project roots.

## Artifact Index

- Baseline: `runtime/background-remover/validation/user-cases-2026-09-08`.
- New experiments: `runtime/background-remover/validation/hardening-2026-09-08`.
- Source: existing `background_remove_*.py`, native page and focused tests.
- Production model catalog/licenses: `tools/background_remover` only after a
  provenance and quality decision. Runtime downloads stay ignored.

## Lookbacks

Initial: the problem is representation/model suitability and missing correction
controls, not runtime installation. Baseline source, docs and actual cases were
reviewed. A large test count previously established lifecycle correctness, not
general segmentation accuracy. Continue with a bounded comparison before UI work.

M1 lookback: BiRefNet tiny fixed the gap by deleting a large part of the tail.
Peak process RSS was5.25GB on the first case and6.18GB across two reused-session
cases, with9.5/6.7s including output processing. Rejected for product use. Evidence:
`general-trial.json` and `character-general-comparison.png` in the new experiment
folder. No new model/runtime dependency will ship.

One mask-guided OpenCV GrabCut trial (1400px maximum edge, three iterations,
alpha>=240 fixed foreground, alpha<8 fixed background) preserved the tail and
removed most trapped background in1.53s. A white fragment still survives. Continue
as optional refined-illustration processing, with actual fixture regressions
required before final defaults. This uses existing OpenCV, not copied external
code; algorithm reference: https://docs.opencv.org/4.x/d8/d83/tutorial_py_grabcut.html

Architecture checkpoint: separate flat-colour extraction from learned subject
segmentation; keep existing-alpha preservation and CPU worker lifecycle. Add an
explicit near-empty warning and undoable, persisted mask corrections. No per-image
patches or automatic largest-subject deletion. General-model expansion stops here.

M2/M3 lookback:
1. Still solving local background removal, including the two supplied failures.
2. Existing ISNet processing, OpenCV, upscaler lifecycle and Qt controls were used;
   the larger general model was not silently substituted.
3. Refined mode regressed a simple blue-grey mascot fixture (IoU 0.98917 to
   0.97672; alpha error 1.85 to 3.41). This is an algorithm tradeoff, not missing
   tuning. Anime (soft edges) therefore remains the default and exactly matches
   the frozen baseline. Refinement is an explicit option for difficult gaps.
4. F1 near-white logo details survive (>99.9% at alpha >=128), the red background
   disappears, and character tail/gap handling was visually inspected. Real UI
   erase/restore/undo/redo and a zoomed connected-colour correction were verified
   against original-resolution pixels, not only preview thumbnails.
5. One model, three modes, one bounded correction document. No generic editor,
   model chooser, generator rewrite or release infrastructure was added.
6. Aggressive largest-component filtering remains rejected. Refined mode is not
   repeatedly tuned against one image after its tradeoff became clear.
7. Automatic segmentation alone cannot infer every intended white fragment or
   same-colour logo hole. A correction workflow is necessary, not a model claim.
8. The best competing approach is a larger general model, but this trial failed
   quality and memory constraints; keep the lighter optional refinement.
9. Continue only with regression, lifecycle, compatibility and resource checks.

UI-test lookback: a recreated service needed an application-owned lifetime. The
later zoomed test passed NumPy scalar values that Qt rejected, leaving the target
offscreen; native Python floats and explicit assignment assertions fixed the
test. Queued QML bindings also require a short event-loop turn after a completed
service operation. No failing pixel assertion or QML warning was suppressed.

## Hardening Evidence

- `workflow-20260908-112715/results.json`: 27 actual offscreen UI checks passed;
  no QML errors. Includes supplied F1/character, near-empty warning, logo mode
  with AI preparation forbidden, brush/undo/redo, persisted resume, 4x wand,
  save/source protection, 8 themes at 960x600 and 1600x1100, cancellation/retry
  and app shutdown with an active real worker. Screenshots are in that run.
- `resilience-20260908-113020/results.json`: 9 successful CPU jobs, offline
  missing-model failure and recovery, missing/corrupt runtime repair, Unicode
  path and identical repeat hashes. Faults used a disposable cache copy, removed
  after testing. Working DIRTY cache was not damaged. Worker peaks 724-782 MiB;
  parent during repeats 58.6-59.0 MiB. No worker survived a completed operation.
- `edit-stress-20260908-113235/results.json`: eight 4000x4000 edits through the
  service, 1.08-1.22 seconds each, event-loop gaps <=47ms, retained memory
  72.5-73.2 MiB, temporary peaks <=499 MiB. A reduced history cap exercised pruning.
  A separate Python process reopened, undid/redid and exported identical pixels.
- All paths above are beneath `runtime/background-remover/validation` and are
  private local evidence. Earlier failed workflow runs remain as audit evidence.

## Final Verification and Stop State

- 717 regression tests passed in 53.283 seconds, including 54 focused removal
  and correction tests: `hardening-2026-09-08/full-regression-verified.txt`.
  The previous run's two failures correctly caught missing hover help and the
  terminal-theme corner convention; both were fixed in the new controls.
- Release-dependency compatibility: all 54 focused tests passed with Pillow
  12.3.0, and the final 27-check real UI workflow passed with no QML errors:
  `hardening-2026-09-08/pillow-12.3-unit-tests-verified.txt` and
  `workflow-20260908-114216/results.json`. Foreground/alpha baseline metrics
  match Pillow 11.3.0 exactly. Both supplied cases and corrections were rerun.
- This compatibility pass caught a real process-lifecycle edge case: Windows
  virtual-environment Python is a redirector, so its child holds the allocations.
  The 2 GiB cap now measures the owned process tree, not only the launcher PID.
  Actual low-limit failure/reaping passes under both Python launch paths.
- Source PNG SHA-256 values still match the frozen baseline. No source image,
  CLEAN, Native, game, save, generator or unrelated feature was changed.
- `git diff --check` passed. The known pre-existing suite shutdown warning about
  184 PySide/Python uncollectable objects is unchanged from the baseline; it is
  not hidden or claimed fixed. Independent worker/repeated-edit checks show
  no surviving workers or continuing memory growth in the tested runs.
- The rejected 224 MB BiRefNet trial download is removed after validation;
  its provenance/hash, metrics and comparison images remain in the experiment
  directory. No new model was added to the product catalog or dependencies.

Final lookback:
1. The reported logo loss, trapped background and missing correction workflow
   are addressed. This is still only a local background-removal feature.
2. Existing model, OpenCV, dependency isolation, theming and report paths remain
   authoritative. No duplicate application or generator branch was created.
3. Remaining uncertainty is semantic segmentation quality and machine coverage,
   not an uninvestigated local failure or only a proxy-score improvement.
4. Real images, exact pixel checks, UI paths, reopened files, separate-process
   recovery and failure injection all contributed evidence.
5. Additional model exploration has stopped; further complexity is not justified
   by the rejected larger model or the optional refinement tradeoff.
6. No prior failed model/cleanup approach is being repeated under a new name.
7. One-click perfection on arbitrary textured art is not a valid assumption.
8. The alternative is larger segmentation or guided models, deferred until a
   broader labeled dataset demonstrates value at acceptable resource cost.
9. Stop implementation here. DIRTY is ready for user testing/promotion decision.
   No push, version bump, CLEAN promotion or release bundle was performed.

Local verification covers Windows x64 on this machine, Python 3.12, both tested
Pillow versions and all current themes. It is not a multi-machine certification.
Automatic illustration output may retain fragments; the supplied difficult case
was verified with an explicit connected-colour correction. Flat-colour removal
cannot automatically distinguish intended foreground using the exact key colour.
These limits are user-facing choices, not silently hidden fallbacks.

## Approved Promotion Checkpoint: 3.1.64

On 2026-09-08 Hestia approved promotion with the random ten-image splash pool.
The earlier DIRTY-only stop state above records the completed hardening stage,
not a restriction on this approved promotion. The combined DIRTY regression
passed all 719 tests in 53.287 seconds; the baseline shutdown warning is unchanged.
Evidence: `runtime/splash-validation/2026-09-08/dirty-regression.txt`.

Promotion is limited to the background remover, splash assets and selection,
associated tests/docs and version metadata. The personal Native instance,
unpublished Discord changelog Worker and generator research are excluded.
There is no public release bundle in this update. CLEAN is tested before the
main push, and the existing quality-gated signed channel publishes the update.
The opt-in workflow harness accepts `KFPS_BG_TEST_ENGINE_ROOT` to reuse an
existing verified engine cache without duplicating dependencies.

CLEAN promotion verification passed on 2026-09-08:
- 719 regression tests, 52.943 seconds, at
  `runtime/splash-validation/2026-09-08/clean-regression.txt`.
- 27 actual-shell workflow checks, including the supplied difficult inputs,
  persisted corrections, save/source protection, eight themes at two window
  sizes, cancellation/retry and active-worker shutdown. Zero operation or QML
  errors: `runtime/background-remover/validation/workflow-20260908-131912/results.json`.
- The 54 promoted source, asset and documentation files were SHA-256 compared
  against DIRTY. Runtime evidence and private test images are not promoted.
