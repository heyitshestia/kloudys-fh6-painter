# FH6 Import And Vinyl Group Setup Guide

This guide explains the FH6 side in detail. If import fails, read this before assuming the JSON is bad.

The importer can only write correctly when FH6 is in the exact expected editor state.

## The Short Version

1. Start FH6 on the same Windows PC as the app.
2. Open Vinyl Group Editor.
3. Load your saved 3000-layer plain white circle template.
4. If you just created it, save it once, leave/reopen it, then ungroup it.
5. Do not switch menus.
6. Enter `3000` as the exact template layer count in the app unless you intentionally opened a different template.
7. Pick a finalized JSON from `finals/`, or choose another compatible JSON manually.
8. Click `Auto-locate FH6 template` if needed.
9. Click `Import JSON into FH6`.

## Important Words

| Word | Meaning |
| --- | --- |
| Vinyl group | A group of vinyl layers inside FH6. |
| Template | A prepared vinyl group with many simple placeholder layers. |
| Layer count | The exact number of layers in the current open FH6 template group. |
| Ungrouped | The template's layers are individually editable, not nested inside another group. |
| Final JSON | Import-ready JSON written by the app in `finals/`. |
| Raw checkpoint | Internal generator JSON in `checkpoints/`; not the recommended import target. |
| Mask layers | Extra non-art layers used by the importer for FH cover/apply behavior. |
| Auto-locate | The app scanning FH6 memory to find the live editable layer table. |

## Why FH6 Setup Matters

The importer writes directly into the currently open FH6 editor layer table.

That means the app must find the exact live table for the group you are editing. If FH6 is in the wrong menu, the group is still grouped, the layer count is wrong, or the active editor table is stale, the importer should stop before writing.

This is why most import errors are editor-state errors, not generator errors.

## Template Layer Budget

Default import uses the full template for drawable art layers. Finalize Checkpoints keeps transparent-source geometry inside the PNG canvas, so current imports do not need FH border masks.

Formula:

```text
usable drawable layers = template layer count
```

Examples:

| Template layer count in FH6 | Usable art shapes in default mode |
| ---: | ---: |
| 500 | 500 |
| 750 | 750 |
| 1000 | 1000 |
| 1500 | 1500 |
| 2000 | 2000 |
| 2500 | 2500 |
| 3000 | 3000 |

Legacy 4-mask import remains available in Settings as a fallback test mode, but it can make underlying stacked vinyls transparent.

## Which JSON Should You Import?

Use:

```text
imgs/generated/<job>/finals/<file>v2.json
```

Do not normally import:

```text
imgs/generated/<job>/checkpoints/
```

The Import tab hides raw checkpoints because final JSONs are safer:

- capped to template budget
- optionally edge-repaired
- scored
- previewed
- reported

## Creating A Template Group In FH6

The app needs a group with enough layers already present. The importer changes existing layers; it does not create thousands of brand-new FH6 layers from nothing.

### Recommended Template Type

Use a simple one-shape placeholder template.

Common template:

```text
3000 simple plain white circle layers
```

Create this template once, save it, leave/reopen it before first use, then ungroup it before importing. The saved 3000-circle template is reusable; the importer writes into the open copy and trims the imported result to the JSON's used layer count.

The exact placeholder art does not matter as much as:

- the layer count is correct
- the layers are editable
- the group is ungrouped
- FH6 is in the right editor state
- the template was saved/reopened once after creation

### Why A Template Is Needed

The importer writes over existing FH6 layer slots.

If your group has 750 layers, the app can only write into those 750 layer slots. It cannot safely import 2000 layers into a 750-layer group.

## Opening The Correct FH6 Screen

You need to be inside the vinyl group editor, editing the template group itself.

Correct state:

- FH6 is running.
- You are in the Vinyl Group Editor.
- The template group is open.
- Individual layers are visible/editable.
- You can select layer 1, layer 2, etc.

Wrong states:

- applying a vinyl to the car
- browsing saved vinyl groups
- editing a livery outside the group editor
- template is selected as one grouped object
- nested group is still grouped
- wrong duplicate group is selected

## Ungrouping The Template

The template must be ungrouped.

Meaning:

- FH6 must expose individual layer slots.
- The importer must be able to access layer 1, layer 2, layer 3, etc.

If the template is still grouped, the importer may report something like:

```text
ERROR: You probably forgot to ungroup one of your vinyls.
Also ensure you are in the Vinyl Group Editor, not applying the vinyl or a livery to the car.
```

Even if you think it is ungrouped, check again:

1. Click/select the template.
2. Confirm the editor shows individual layers.
3. Confirm you are not selecting a nested group.
4. Confirm duplicate groups are not stacked above the intended one.

## Exact Layer Count

Enter the exact total layer count shown by FH6 for the template.

Examples:

- If the group has 750 layers, enter `750`.
- If the group has 2000 layers, enter `2000`.
- If the group has 2004 layers, enter `2004`.

Do not enter the JSON shape count unless it equals the FH6 template count.

Why this matters:

- The locator uses layer count to validate possible memory tables.
- Wrong count can find no table.
- Wrong count can reject the correct table.
- Wrong count can accidentally match stale data.

## Auto-Locate FH6 Template

Click:

```text
Auto-locate FH6 template
```

Use it when:

- first import after starting FH6
- FH6 was restarted
- you changed groups
- import says stale table
- import says slot null
- process changed

During auto-locate:

- keep FH6 in Vinyl Group Editor
- do not change menus
- do not switch groups
- do not close the editor

Good result:

```text
FH6 template located and verified.
```

## Importing

After auto-locate or after the app verifies the template:

1. Make sure the right final JSON is highlighted.
2. Make sure template layer count is exact.
3. Click `Import JSON into FH6`.
4. Do not touch FH6 while it writes.
5. Wait for `DONE!` or success message.

During import, the log may show:

```text
Writing layer 1/2000
Writing layer 100/2000
Writing layer 200/2000
...
DONE!
```

## Border Mask Behavior

Current default:

```text
No FH border masks
```

Finalize Checkpoints keeps transparent-source geometry inside the PNG canvas, so the importer does not reserve separate border-mask layers.

Uses every template layer for art.

Pros:

- maximum drawable layers
- does not punch transparent strips through stacked vinyls
- default behavior

## Common Import Errors

### "You probably forgot to ungroup one of your vinyls"

Likely causes:

- template is grouped
- you are in wrong FH6 screen
- you are applying a vinyl/livery instead of editing the group
- layer count is wrong
- selected group is not the intended template

Fix:

1. Return to Vinyl Group Editor.
2. Open the template group.
3. Ungroup it.
4. Verify individual layers are visible/editable.
5. Enter exact layer count.
6. Auto-locate again.

### "Layer slot resolved to a null pointer"

Meaning:

The app found something that looked like a layer table, but one of the expected layer slots was invalid.

Likely causes:

- stale memory table
- wrong group open
- duplicate group/template above the intended one
- FH6 menu changed after locating
- wrong layer count

Fix:

1. Stay in Vinyl Group Editor.
2. Reopen the exact group/template.
3. Remove duplicate groups/templates above it if needed.
4. Confirm exact layer count.
5. Click Auto-Locate again.
6. Import again.

### "No safe FH6 layer group found"

Meaning:

The locator scanned but did not find a table that passed safety checks.

Likely causes:

- wrong menu
- wrong count
- group not open
- FH6 process changed/restarted
- app lacks permission

Fix:

1. Check FH6 is running.
2. Check you are in Vinyl Group Editor.
3. Check layer count.
4. Run app as administrator.
5. Auto-locate again.

### "Game process not found"

Fix:

1. Start FH6.
2. Wait until you are in game/editor.
3. Click Refresh in the app.
4. If still missing, run app as administrator.

## Duplicate Groups And Wrong Table Problems

If multiple template groups are stacked at the top of the editor, the locator can get confused or validate the wrong table.

Symptoms:

- locator succeeds but import writes nowhere useful
- slot null error
- stale table warning
- imports into an unexpected group

Fix:

- keep only the template group you intend to import into
- remove duplicate template groups above it
- reopen the group after cleaning
- auto-locate again

## After Import

After import finishes:

1. Look at the vinyl in FH6.
2. Confirm it appears correctly.
3. Save/apply using FH6's normal workflow.
4. If something looks wrong, do not overwrite a good saved group until you understand why.

If the result is clipped:

- JSON exceeded usable layer count
- template layer count was too small
- mask mode/layer budget mismatch

If the result is in the wrong place/scale:

- wrong template
- wrong editor state
- wrong source dimensions/settings

## Best Practices

- Use one clean template group.
- Know the exact layer count.
- Do not switch FH6 menus after auto-locate.
- Use Full legacy masks unless testing.
- Import final JSONs, not raw checkpoints.
- Keep generated reports when asking for help.
- Run the app as administrator if FH6 memory access fails.

## Help Checklist

If asking for help, provide:

- screenshot of FH6 editor state
- exact template layer count
- selected final JSON filename
- app log error text
- report JSON from `reports/`
- whether template is ungrouped
- whether duplicate groups exist above it
- whether app is running as administrator
