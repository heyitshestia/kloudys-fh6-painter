# Generator Benchmark Plan

Purpose: stop guessing preset values by running repeatable style/speed/layer tests, recording the results, and ranking settings from data.

## What Gets Tested

Each run combines:

- Style: `flat`, `shaded`, `gradient`
- Speed tier: `fast`, `balanced`, `high`, `extreme`
- Target layers: normally `500`, `1000`, `2000`, `3000`
- Source image: every image supplied to the benchmark runner

The benchmark creates temporary `.ini` files for each combination. It does not edit the shipped presets.

The runner is:

```text
tools/benchmark_generator_settings.py
```

## Setting Model

Target layers are the vinyl drawing budget.

Max resolution is the largest source side the raw generator sees. It should grow slowly with layer count, not linearly.

Random samples are the main search effort. They should scale mostly with speed/quality tier and source style.

Mutated samples polish a good random candidate. They should stay a small fraction of random samples.

V2 score size controls how much detail finalization uses when scoring, pruning, repair, and cleanup happen. This is separate from raw `maxResolution`.

## Current Formula Direction

Max resolution uses a slow growth curve:

```text
base = 650 + 24 * sqrt(target_layers)
maxResolution = base * style_factor * speed_factor
```

Then it is clamped by style.

Style factors:

```text
flat:     0.85
shaded:   1.05
gradient: 1.20
```

Speed factors:

```text
fast:     0.85
balanced: 0.95
high:     1.00
extreme:  1.12
```

Random and mutated samples are anchored to practical known-good values, then scaled by speed tier.

## Style Definitions

`flat`

- Intended for logos, decals, hard borders, mascot art, text-like shapes, and broad flat color panels.
- Uses `shapeMode = mixed_edge_bias`.
- Uses `v2PreprocessMode = luma_bands`.
- Uses `forceOpaqueShapes = true`.
- Uses lower max resolution because logos need clean decisions more than tiny texture chasing.

`shaded`

- Intended for anime, characters, skin, hair, eyes, and mixed linework.
- Uses `shapeMode = mixed_smart_detail`.
- Uses `v2PreprocessMode = none`.
- Uses `forceOpaqueShapes = true`.
- Uses medium-high max resolution to keep eyes, linework, and hair detail visible.

`gradient`

- Intended for soft ramps, glossy shading, blush, skin gradients, painterly blends, and dark-to-light transitions.
- Uses `shapeMode = mixed_soft_detail`.
- Uses `v2PreprocessMode = none`.
- Uses `forceOpaqueShapes = false`.
- Uses the highest max resolution and alpha-friendly output because gradients need softness more than hard posterized cuts.

## Speed Tier Definitions

`fast`

- Low sample count.
- Lower max resolution.
- Good for finding if a style fits an image before spending time.

`balanced`

- Medium sample count.
- Slightly lower than high max resolution.
- Main candidate for practical daily use if quality is acceptable.

`high`

- Current target-quality baseline.
- Closest to the manually chosen values discussed for shipped presets.

`extreme`

- Higher samples and resolution.
- Use to prove whether more effort is actually helping or just wasting time.

## Current Anchor Values

Flat/logo anchors:

| Layers | Max resolution | Random samples | Mutated samples |
| --- | ---: | ---: | ---: |
| 500 | 1000 | 280000 | 12000 |
| 1000 | 1200 | 380000 | 16000 |
| 2000 | 1400 | 520000 | 22000 |
| 3000 | 1600 | 650000 | 28000 |

Shaded art anchors:

| Layers | Max resolution | Random samples | Mutated samples |
| --- | ---: | ---: | ---: |
| 500 | 1200 | 320000 | 14000 |
| 1000 | 1500 | 430000 | 20000 |
| 2000 | 1800 | 560000 | 26000 |
| 3000 | 2100 | 720000 | 34000 |

Gradient anchors:

| Layers | Max resolution | Random samples | Mutated samples |
| --- | ---: | ---: | ---: |
| 500 | 1400 | 380000 | 18000 |
| 1000 | 1800 | 520000 | 24000 |
| 2500 | 2200 | 680000 | 32000 |
| 3000 | 2500 | 860000 | 42000 |

The script interpolates between anchors when testing intermediate layer counts.

## Why V2 Score Size Is Included

Raw generation uses `maxResolution`, but V2 finalization normally scores at a separate `score-size`.

This matters because finalization does important work:

- checkpoint scoring
- pruning/capping
- Edge Repair
- covered layer cleanup
- final error ranking

If raw generation sees 1800-2200 detail but V2 judges at 640, V2 may miss some small detail. The benchmark therefore records and varies style-specific score size.

## Ranking

The benchmark writes all raw results to CSV, then creates ranked summaries.

Primary rank is lowest final V2 error.

Balanced rank also considers runtime and layer count, so it can find settings that are almost as accurate but much faster.

The balanced score is deliberately conservative. It does not replace visual judgment. It only helps sort rows so the best candidates are near the top.

## Output Files

The runner writes to:

```text
runtime/benchmarks/<timestamp>/
```

Important files:

```text
benchmark_runs.csv
best_by_image.csv
best_by_style_layer.csv
best_by_image_style.csv
best_overall.csv
planned_runs.csv
settings/
runs/
logs/
best_settings_summary.json
best_overall_contact_sheet.jpg
```

## How To Run

Plan only, no generator work:

```text
python tools/benchmark_generator_settings.py --images Images --plan-only
```

Small smoke test:

```text
python tools/benchmark_generator_settings.py --profile smoke
```

Real benchmark:

```text
python tools/benchmark_generator_settings.py --images Images --layers 500,1000,2000 --tiers fast,balanced,high --styles flat,shaded,gradient
```

Comprehensive benchmark:

```text
python tools/benchmark_generator_settings.py --images Images --profile full
```

Exhaustive benchmark:

```text
python tools/benchmark_generator_settings.py --images Images --profile exhaustive
```

Limit the run count while testing:

```text
python tools/benchmark_generator_settings.py --images Images --max-runs 6
```

Reduced-budget real-image spot check:

```text
python tools/benchmark_generator_settings.py --images Images --layers 100 --styles flat,shaded,gradient --tiers fast --sample-scale 0.03 --mutation-scale 0.05 --max-runs 3
```

Resume an interrupted benchmark:

```text
python tools/benchmark_generator_settings.py --bench-dir runtime/benchmarks/20260527-120000 --resume
```

## How Results Should Be Used

Do not blindly copy the single lowest-error row into production.

Use the CSV to compare:

- Is the lower error visually meaningful?
- Did runtime explode for tiny improvement?
- Did a style consistently win on matching source types?
- Did V2 repair or cleanup remove too much detail?
- Did high `maxResolution` improve detail or just create blockiness?

After enough images are tested, update shipped presets from the best stable clusters, not from one lucky image.

## Visual Spot Check Workflow

After a benchmark, open:

```text
best_overall_contact_sheet.jpg
```

Then compare the best few rows against:

```text
best_overall.csv
best_by_image.csv
best_by_image_style.csv
best_by_style_layer.csv
```

Good candidates should satisfy all of these:

- low final error
- visually close source silhouette
- no obvious unwanted blocky top-layer rectangles
- no major transparent/discolored fills
- runtime is acceptable
- same style/tier wins across multiple similar images

If the best-error row looks worse than a slightly higher-error row, prefer the visually better row and keep the evidence. The score is a guide, not the final judge.

## What To Change After Testing

If one style/tier/layer cluster wins repeatedly, update:

```text
settings/a.flat-colors.ini
settings/b.shaded-art.ini
settings/c.gradients.ini
```

Possible future app improvement:

```text
Style dropdown + Speed dropdown + Layer dropdown
```

Instead of maintaining only three static preset files, the app could calculate:

```text
maxResolution
randomSamples
mutatedSamples
score-size
shapeMode
Luma Prep
forceOpaqueShapes
```

from the same benchmark-backed formula.
