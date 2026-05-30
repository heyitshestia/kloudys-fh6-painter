# Generator V6 Next Steps

These are the next high-impact improvements to revisit after current release/support issues are handled.

1. Preset polish by image type: tune presets for anime, painterly art, logos, photos, and flat decals instead of treating every input the same.
2. Better source cleanup before generation: improve alpha cleanup, tiny-island removal, near-transparent junk removal, and optional edge-preserving denoise.
3. Smarter final pruning: prevent removal of visually important opacity/detail layers by checking local visual impact before deleting.
4. Detail-preservation pass: reserve late layers for eyes, text, hair strands, outlines, hands, fingers, and other small high-contrast regions.
5. Adaptive sample scaling: scale effort from edge density, visible alpha area, color count, target layers, and image complexity.
6. Better gradient handling: use larger soft shapes early for smooth shading, then smaller opaque detail later to avoid blocky or milky gradients.
7. Shape-type intelligence: prefer rectangles for flat fills, stripes, hard borders, and logo-like regions; prefer ellipses for curves, skin, hair, and soft shading.
