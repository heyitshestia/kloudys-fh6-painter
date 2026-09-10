# Editor Performance Hardening, 3.1.73

## Scope

Preserve Fabric, native/KFPS integration, shape identities, flat game exports,
editable groups, independent assets, localization, settings and recovery cadence.
This patch removes redundant work rather than changing the renderer or file format.

## Changes

- Skip only Fabric's hidden on-screen scene pass during an active GPU preview.
  Keep its lifecycle, hit testing, selection controls and other render contexts.
- Coalesce GPU requests, compare mask order against one stack snapshot, and update
  helper coordinates only when their transform or viewport changes.
- Use linear mask validation, visible-row geometry refreshes, cached history time
  formatting and known-object nudge history capture. Structural changes and final
  exports still perform their authoritative full validation.
- Cancel superseded JSON browser requests; do not allow a stale response to win.
  Reuse selection rows and privately revalidate unchanged local thumbnails.
- Remove the 16MP reference rejection. Retain original source and sampling pixels;
  resize only the GPU upload when a device texture dimension limit requires it.
  Temporary sampling/upload canvases release their backing storage. Original
  decoded-image memory still grows with pixel count. The 20 MiB source budget,
  25 MiB project budget and browser image/canvas limits still apply.
- Use K-FPS as the Korean heading, leaving the English heading unchanged.

## Matched Native Measurements

Real QtWebEngine, 1440x900, eight release-to-paint samples per fixture on one
Windows desktop. Baseline is 3.1.72; final patch has two isolated repeats.
Numbers are medians in milliseconds, not a guaranteed user frame rate.

| Workload | Baseline | Patched repeat 1 | Patched repeat 2 |
| --- | ---: | ---: | ---: |
| 3,000 primitives, one selected | 57.6 | 36.3 | 34.2 |
| 3,000 layers, 999 masks | 182.6 | 47.8 | 47.4 |
| 1,400 mixed gradient shapes | 49.4 | 24.0 | 29.8 |
| 3,000 layers, 1,000 selected | 56.2 | 45.2 | 43.7 |
| 3,000 layers, synthetic 4x CPU throttle | 356.2 | 205.2 | 197.1 |

The separate 500-layer drag median did not improve uniformly (22.7 to 27.1 ms,
same 28.3 ms maximum). Heavy throttled interactions still visibly pause.

## Verification And Limits

The 21-minute uninterrupted 3,000-layer session completed 2,967 edit cycles,
with 176 masks, 375 gradient resources, 150 groups, selections up to 1,000,
2K/4K reference replacement, five project readbacks and 21 recovery readbacks.
Retained JavaScript heap was 43.55 MiB at minute 5 and 41.67 MiB at minute 20.
No exponential growth was reproduced. Forced GC checkpoints and one machine do
not establish leak-free operation; native host/renderer private memory peaked
around 2.27 GiB, substantially above JavaScript heap alone.

Native checks cover all 1,400 shape slots at four zooms, geometry/export identity,
mask/gradient pixels, history, context loss, recovery errors, save/restart,
favorites/assets and English/Korean workflows. Large-reference regression uses
the actual file-input path with 6000x4000 and 8192x4096 PNGs, a one-pixel color
marker, GPU pixel checks, a simulated smaller device texture limit, real project
save/readback/reopen and persisted recovery after renderer reload.

One legacy pointer-transform test fails its tight numerical tolerance identically
on the frozen baseline and patch. Its assertion was not weakened. The dedicated
native transform/history/shape suites pass; that legacy test remains a known gap.
Cold folder scans and thumbnail generation remain possible costs; cancelling a
client request does not cancel a filesystem scan already running on the server.
