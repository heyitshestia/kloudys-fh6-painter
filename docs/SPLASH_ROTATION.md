# Random Mini Kloudy Splash Artwork

## Scope

2026-09-08, KFPS 3.1.64: include the nine user-supplied transparent PNGs and the
existing Mini Kloudy artwork. Random selection happens once at splash creation;
it does not cycle images during startup, persist launch history, or load artwork
on animation ticks. Random repeats between launches are possible.

The existing circular splash, text, progress and opposing animated rings remain
unchanged. Only the selected image is decoded, unless a candidate is missing or
invalid. A randomized candidate order gives each valid image equal opportunity.
Invalid files, files over 16 MiB, and dimensions over 16MP are skipped. If none
load, the existing letter-K fallback preserves startup and progress reporting.

## Assets and Tests

- Source: `KFPS.UI/src/kfps_ui/startup_splash.py`.
- New assets/provenance: `KFPS.UI/assets/mini-kloudy-splash`.
- Existing artwork: `KFPS.UI/assets/mini-kloudy.png`, not duplicated.
- All nine supplied files were copied byte-for-byte; source hashes were compared.
- Automated checks: `KFPS.UI/tests/test_startup_splash.py` loads every candidate,
  validates transparency, label separation, fixed artwork during animation,
  missing/corrupt fallback, progress and timer lifecycle.
- Offscreen visual evidence: `runtime/splash-validation/2026-09-08/all-ten.png`.
  The harness registers the Windows Segoe UI font for faithful offscreen rendering.
  No desktop focus is taken. The actual Windows splash uses system font lookup.

## Promotion

This feature and the locally validated background remover are approved for CLEAN,
main and a version bump to 3.1.64. No public release or downloadable bundle was
requested. The existing signed-update publication workflow handles normal version
updates. Native Updated Local and the unrelated Discord changelog Worker are out
of scope. The background-remover hardening report records its pre-promotion tests.
