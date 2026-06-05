KFPS FH6 Research Dumper

Purpose:
This creates a read-only memory report for the currently open FH6 vinyl/group.
It does not import, export, poke, patch, or write anything to the game.
It also saves raw candidate-local memory chunks around the best detected group,
table, and layer regions so KFPS import/export locating can be improved later.

Before running:
1. Open Forza Horizon 6.
2. Open the vinyl/group you want checked in the vinyl editor.
3. Know the visible layer count shown by the game.
4. Close KFPS if it is currently importing/exporting.

How to run:
1. Double-click Run_FH6_Research_Dump.bat.
2. Press 1, 2, or 3 for the current vinyl state:
   1 = ungrouped shapes
   2 = one grouped vinyl
   3 = grouped groups / nested groups
3. Enter the visible layer count, for example: 3000
4. Wait until it says ZIP ready.
5. Send the newest .zip from the captures folder.

If it fails:
- Run it as Administrator if Windows blocks process reading.
- Make sure FH6 is open and the vinyl/group is currently loaded.
- Make sure the layer count is exact.
- Pick the closest state option. Do not rename the output manually.
- If Python is missing, run it from a KFPS standalone folder or install Python 3.12.

What it saves:
- capture.json: scanner details for offline debugging.
- candidate-summary.json: short list of likely group/table candidates.
- raw-region-chunks.json: index of the raw binary chunks.
- raw-region-chunks/*.bin: larger raw bytes around candidate group/table/layer areas.
- notes.txt: human-readable summary.

Privacy:
The report includes FH6 process memory around likely vinyl candidates. The raw chunk
files can be larger and may include nearby unrelated FH6 process bytes. Do not run it
while private unrelated apps are open if you are worried about memory captures. It is
meant only for FH6 vinyl/import debugging and should only be shared with trusted KFPS
debugging contacts.
