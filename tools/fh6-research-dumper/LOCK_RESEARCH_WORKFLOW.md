# FH6 Locked/Unlocked Research Dumper Workflow

This tool is read-only. It does not write to Forza and does not export a usable vinyl JSON. It collects memory evidence so KFPS can reliably compare unlocked flat vinyls against locked one-group vinyls.

## Current Research Rule

This dumper pass uses the simple tester-facing labels:

- `Unlocked`: assumed fully ungrouped / flat.
- `Locked`: assumed one grouped vinyl.
- `Unknown`: only when the tester cannot confidently choose either.

The capture still records both access state and grouping state internally so the analyzer can verify whether the memory graph matches those assumptions.

## User Capture Steps

1. Open FH6 and enter the vinyl editor.
2. Open exactly one vinyl state to inspect.
3. Run `Run_FH6_Research_Dump.bat`.
4. Choose the vinyl state:
   - `1` for unlocked / ungrouped.
   - `2` for locked / one group.
   - `3` if not sure.
5. Enter the visible FH6 layer count.
6. Wait until the script says the ZIP is ready.
7. Send the newest ZIP from the `captures` folder.

Run the dumper once per vinyl. Do not change the vinyl while the dumper is scanning.

## What The Dumper Saves

Each capture folder contains:

- `capture.json`: full research data.
- `candidate-summary.json`: compact candidate summary with graph/orphan fields.
- `raw-region-chunks/`: raw surrounding memory chunks for deeper manual analysis.
- `raw-region-chunks.json`: manifest for the raw chunks.
- `notes.txt`: human-readable notes template.

The batch also updates:

- `lock-research-analysis.json`
- `lock-research-analysis.md`

The filename is kept for compatibility, but the report now includes both locked-vs-unlocked and grouped-vs-ungrouped graph analysis.

## Good Test Set

Minimum useful set:

- 3 unlocked captures.
- 3 locked captures.
- At least one capture after restarting FH6.

Better set:

- 5-10 unlocked captures.
- 5-10 locked captures.
- A mix of small, medium, and high layer counts.
- Similar layer counts in both states where possible.

## How To Interpret Results

Open `captures/lock-research-analysis.md`.

The strongest graph evidence is whether the selected candidate is:

- `flat_orphan=True`
- `parent=False`
- `children=False`
- `exact_vector=True`

Expected behavior:

- Unlocked captures should produce clean flat-orphan candidates.
- Locked captures are expected to behave like one grouped vinyl. If they still appear as clean flat orphans, then lock status is not represented by this graph relationship alone.

If locked captures still appear as clean flat orphans, then either the game exposes the selected child table as flat in memory, or the dumper is not yet collecting enough relationship data.

## Current Safety Rule

Until this is proven, the exporter should require users to fully ungroup before exporting.

If the locator or candidate validation is weak, the app should refuse export instead of producing a partial or questionable export.
