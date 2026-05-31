# Generator V7 Notes

V7 is the promoted prototype generator filename: `KloudysGeneratorV7.exe`.

The current release treats V7 raw geometry as the primary result. Legacy Edge Repair stays disabled in the stock presets because visual tests on anime/digital-art sources repeatedly showed V7 raw checkpoints preserving eyes, hair, corners, and soft shading better than the old V2 repair pass.

## 2026-05-31 Speed Prototype Findings

The current V7 build includes optional two-stage random scoring. It first scores the large random candidate pool coarsely, keeps the best candidates, then exact-scores only that smaller finalist set. This preserves the same visual search path better than hard alpha clamping or mutation early-exit.

Benchmark images used for this pass were large detailed character/digital-art sources: `beachday.png`, `mikupolice.png`, and `angelbelow.png`.

Key result: on a 1000-layer `mikupolice.png` validation run, `randomSamples=220000` with two-stage random scoring was about 21% faster than `randomSamples=280000` with effectively identical preview/source error. The stock presets now use two-stage random scoring with `randomRefineTopK=2048`.

Rejected options:

1. Strict alpha-safe candidate clamping was faster but visibly damaged thin hair/edge details.
2. Mutation early-exit reduced detail and should stay off for quality presets.
3. Reducing mutation samples did not produce meaningful speed gains in the tested image set.

## Current Preset Intent

1. `Shaded Character Art` is the default anime/digital-art preset. It uses a 1100px cap, 1500 default layers, stronger late detail sampling, boundary-aware radius, low rectangle share, and opaque shapes.
2. `Flat Colors` is for cel shading, stickers, mascots, and clean panels. It keeps Luma Prep enabled, uses harder edge bias, and allows more rectangle pressure than shaded art.
3. `Smooth Gradients` is for soft shading and painterly ramps. It keeps Luma Prep off, allows alpha, reduces rectangle pressure, and spends more layers when the source needs blending.

## Guardrails

1. Do not re-enable legacy Edge Repair by default unless side-by-side visual tests show a clear improvement.
2. Avoid broad smooth-region penalties without checking faces, eyes, hands, and hair. Earlier tests reduced detail where the source needed small shapes.
3. Keep rectangle share conservative on shaded character art. Rectangles help logos and panels but are visibly wrong on faces and curved shading when overused.
4. Judge raw and finalized checkpoints separately. If final output differs from raw, inspect pruning, flat-color stabilization, and covered-layer cleanup before blaming the generator.

## Next Work Items

1. Add perceptual checkpoint scoring so the app can rank checkpoints closer to human visual preference instead of only raw render error.
2. Add region-of-interest weighting for eyes, faces, hands, text, hair strands, and high-contrast linework.
3. Improve late-stage acceptance so low-value translucent blobs do not replace useful small details.
4. Add contour/edge-seeded candidates as an optional path, especially for line art and hard silhouettes.
5. Expand shape intelligence when more stable FH6 primitive mappings are available.
6. Improve source classification so preset routing can warn when Luma Prep is likely harmful.
7. Keep optional postprocess passes, but gate them per checkpoint and only apply when they improve visual scoring.
