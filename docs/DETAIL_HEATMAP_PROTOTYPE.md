# Detail Heatmap

Status: experimental, opt-in, and intentionally off by default.

## Goal

Add a pre-generation detail focus system so the generator can spend the existing layer budget more deliberately around eyes, linework, small edges, alpha cuts, and other important detail.

## User Flow

The Generate Final Vinyl tab has one automatic detail focus option:

- Automatic Detail Heatmap: detects likely high-detail regions from the source image.

Preview heatmap toggles the live preview between the source image and the detected heatmap before generation.

## Implementation

`detail_heatmap.py` builds deterministic masks from:

- luminance edges
- RGB/color edges
- alpha edges
- local contrast
- dark linework
- highlights
- saturated color edges

The detected mask is saved as `previews/<source>.detail-heatmap.png`.

When enabled, the mask is used in two places:

- A conservative source guide image, saved as `previews/<source>.detail-guided.png`.
- Finalize Checkpoints scoring/repair weighting, so detail-heavy regions are less likely to be pruned or softened.

Default strength is `0.10`. This is intentionally conservative.

## A/B Results

All tests below used 300 target layers and Edge Repair on, only to validate direction quickly.

- Frieren control: `3422.020573`
- Frieren automatic heatmap: `3344.330243`
- Nikke control: `3321.935184`
- Nikke automatic heatmap: `3257.265315`

Lower error is better. Visual checks showed better detail allocation, but not enough certainty to make this default-on.

## Risks

- Heatmaps can trade broad shape accuracy for local detail when layer count is very low.
- Actual benefit is unclear on many images, and results may vary.
- Important tiny details are often better made or cleaned by hand in the external vinyl editor.

## Current Decision

Keep the feature opt-in. The preview-first workflow is important because users can see whether the red/yellow heatmap matches the detail they care about before committing to a run.
