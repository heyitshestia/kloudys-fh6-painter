# QML refinement pass 01

This pass focuses on geometry correctness rather than changing backend behavior.

## Corrected

- Primary and ghost button labels are centered independently of optional left icons and right arrows.
- Button labels shrink safely, elide as a final fallback, and retain explicit minimum heights.
- Text fields, combo boxes, check boxes, switches, and sliders use consistent vertical alignment and scaled padding.
- All reusable controls derive geometry from the active UI scale instead of accumulating integer rounding error.
- Responsive breakpoints operate in logical design units, so changing UI scale activates compact layouts correctly.
- Dashboard rows have explicit sizes when changing between three-column and stacked layouts.
- Dashboard utility rows gain a dense mode at short heights instead of clipping content.
- The sidebar uses a route-aware `ListView` and automatically keeps the active page visible on short windows.
- High-scale dashboard views always begin at the top rather than jumping to the first focusable button.
- Compact and expanded bottom-panel actions use the same centered button contract.

## Validation matrix

The expected manual QA matrix is:

- Window sizes: 1140×720, 1280×720, 1548×970, 1920×1080, 2560×1440.
- UI scales: 0.80, 1.00, 1.15, 1.25, 1.35.
- Pages: Dashboard, Generate, JSON, Editor, Images, Tools, Help, Reports, Update, Settings.

Every page must remain keyboard reachable and vertically scrollable when its controls cannot fit in the available height. No page may introduce horizontal scrolling.
