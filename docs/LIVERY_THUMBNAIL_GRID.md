# Livery Thumbnail Grid

The native Liveries page opens on a searchable thumbnail grid. A single click
selects a local FH6 livery without rendering it. Open 3D Preview, double-click,
or Enter explicitly starts the existing preview path. Back to Liveries releases
the viewer and preserves the selected source. Returning from another page opens
the grid rather than restarting an old preview.

Export Selected creates and verifies the package, then refreshes Saved packages.
It does not open a 3D preview or change the selected source. Opening a preview
remains an explicit action.

## Data And Resource Boundaries

- Each image comes only from that exact C_livery container's bigThumb.webp or
  BigThumb.webp. There is no same-car image guessing or separate cache crawl.
- Existing scan ownership, visibility and export policies remain authoritative.
  Preview-only records are still marked and cannot be exported from the grid.
- Browsing thumbnails requires the save records, not the FH6 game assets. A
  linked installation is still required for a 3D preview.
- Missing, empty, corrupt or over-4-MiB thumbnails show a placeholder. They do not
  trigger rendering, conversion or game writes.
- Images load asynchronously at a bounded 670 x 376 requested size. GridView
  reuses delegates; pooled delegates clear their image source. Qt's global image
  cache is disabled for these images.
- Thumbnail revision URLs use file modification time and length. Rescanning or
  reopening the catalog refreshes the image independently of C_livery changes.
- Search is literal and case-insensitive across title, model code and car ID.
  It filters a proxy model without changing source paths or the durable catalog.
- Exported package contents, the save parser, renderer and installer are unchanged.

## Reference And Provenance

FH6 Assistant v1.4 Source was inspected read-only: scanner.py's _detect_thumbnail,
the thumbnail cards in ui.py, and thumbnail_cache.py. Its original-thumbnail
association was used as a behavioral reference. No explicit license was found;
no reference-project source, assets or dependencies were copied into KFPS.

## Verification

Run from the KFPS root:

```powershell
py -3.12 -m unittest discover -s KFPS.UI/tests -p '*livery*.py'
py -3.12 KFPS.UI/tools/test_livery_grid_workflow.py --output <validation-directory>
```

The native workflow uses isolated settings and temporary fixture records. An
optional --thumbnail-root <ContainersRoot> samples up to 12 original thumbnails
read-only into disposable fixtures. It checks actual Qt image pixels, selection,
search, explicit preview handoff, navigation, missing/broken images, four window
sizes, and virtualized scrolling with 1,500 model rows. Scan/package workers and
3D work are mocked in this focused UI test; the existing livery suite exercises
their contracts. This is not a new end-to-end game import/export qualification.

Evidence dated 2026-09-09 is stored in the external KFPS Documentation workspace,
under Livery Thumbnail Grid 2026-09-09. Version 3.1.71 is delivered through the
signed stable updater after the quality gates pass. No new full release bundle
is included; signed update-data publication is separate from manual bundles.
