KFPS CLiveryGroup RTTI Calibrator

Purpose:
This is a read-only recovery tool for FH6 updates that move/break the fast
CLiveryGroup RTTI locator. A working RTTI locator lets KFPS find live vinyl
groups much faster than broad fallback memory scans.

It does not import, export, poke, patch, or write anything to Forza.

Recommended use:
1. Open Forza Horizon 6.
2. Open a simple white-circle template in the vinyl editor.
3. Prefer the reusable 3000-layer circle template.
4. Double-click Run_CLivery_RTTI_Calibrator.bat.
5. Choose option 1.
6. Press Enter to scan the current count.
7. Add or delete a few simple circles in FH6.
8. Enter the new visible layer count.
9. Repeat scan/change/scan until the tool says LOCKED RTTI.

Menu options:
- Option 1 is the main guided scan/change/scan lock-on workflow.
- Option 2 continuously searches a normal 3000-layer template once per loop.
- Option 3 does the same single-count continuous search with a custom layer count.

Important:
One scan is not enough. The useful evidence is the same RTTI/vtable identity
showing up after controlled count changes. The tool saves only after repeated
evidence across multiple scans and at least two different visible layer counts.

What it saves:
- calibration-results/<timestamp>/clivery-rtti-latest.json
- calibration-results/<timestamp>/clivery-rtti-offsets.txt
- calibration-results/<timestamp>/update-codes.dat when a readable RTTI type name
  was recovered.

Notes:
- RTTI recovery is meant to rebuild the fast locator after an FH6 patch.
- It helps avoid slow fallback scans, but import/export still must validate the
  exact group/table before writing or reading.
- The old FH5 decimal update-code list is included only as legacy pattern hints.
  The strongest evidence is still a live group candidate connected to MSVC RTTI.

Privacy:
This tool only saves addresses, offsets, summaries, and short pattern evidence.
It does not save full memory dumps.
