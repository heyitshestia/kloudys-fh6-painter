# FH6 RTTI and Group Export Findings - 2026-06-05

This document records the current import/export memory-locator research after the June 5 RTTI calibration and grouped/nested export tests. It builds on `FH6_LOCATOR_DUMP_FINDINGS_2026-06-03.md`.

## Current Status

The strongest locator path is now the calibrated FH6 `CLiveryGroup` RTTI profile plus per-group validation. This is much faster and more reliable than broad layout-count scanning when the open vinyl group is a normal live editor object.

Current calibrated FH6 profile in code:

- Update-code/type evidence: `98170067497080`
- RTTI descriptor offset from module base: `0x9e17e20`
- CLiveryGroup vtable offset from module base: `0x6802470`
- Observed base class count during calibration: `4`
- Calibrator also recorded related class-descriptor/self offsets during research: `0x7eb7528` and `0x7eb7500`

The current implementation first validates that the descriptor update-code still matches, then scans writable private memory for groups whose first pointer matches the calibrated vtable. Every candidate must still validate table pointers and layer entries before import/export uses it.

## Why This Matters

The older fallback locator scanned huge process ranges looking for layer-count/table patterns. It worked for many large ungrouped templates but was slow, could miss small groups, and could choose stale/partial candidates after editor refreshes.

The RTTI path changes the problem:

- Find real `CLiveryGroup` objects by vtable identity.
- Read their vector begin/end/capacity fields.
- Validate candidate layer pointers.
- Only then match the requested visible layer count.

This should make normal import/export much faster and should make small double-digit groups feasible once the grouped/nested path is complete.

## Manual Calibration Evidence

The RTTI calibrator was run with controlled live FH6 editor changes. The useful workflow was:

1. Open a simple white-circle template.
2. Scan a known visible layer count.
3. Add or delete a few circles.
4. Enter the new visible layer count.
5. Repeat until the same descriptor/vtable evidence survives multiple counts and an FH6 restart.

Observed stable evidence:

- A 3000-layer white-circle template repeatedly found the same descriptor/vtable identity.
- Controlled counts around 3000, including 3000, 2998, 2996, 2994, 2992, and 2989, kept the same RTTI identity.
- A separate 2000-layer template matched the same identity.
- After restarting FH6 and reopening a 3000-layer template, the same offsets still worked.
- Additional scans after restart did not produce conflicting RTTI evidence.

Conclusion: the current offset profile is strong enough to hard-code as the fast path for this FH6 build, provided every live group/table is still validated before use.

## Export Test Coverage

Recent manual/live tests covered:

- Large ungrouped groups: 3000, 2000, 1000.
- Mixed real designs: 868, 720, 492, 239.
- Grouped small designs: 5, 6, 10, 14.
- Grouped and nested grouped designs, including a 1926-shape mixed vinyl.
- A 1926-shape design exported both ungrouped and grouped/nested for comparison.

Flat/un-grouped export was confirmed to preserve order, shape type, color, scale, rotation, and coordinates against the same design exported through the older flat path.

Grouped/nested export can now locate the top group and recursively flatten child groups into layer pointers. The locator reported examples like:

- Top-level vector entries lower than visible layer count.
- Flattened visible leaf layers equal to requested count.
- Group count greater than one.
- Nesting depth greater than one.

## Current Group/Nested Limitation

Recursive flattened export currently reads child layer pointers correctly, but parent group transforms are not fully solved yet.

The current code applies cumulative parent translation (`x`, `y`) only. This fixed the most obvious "local child coordinates" problem in some cases, but it is not a complete transform composition.

Still missing or not fully proven:

- Parent rotation composition.
- Parent scale composition.
- Parent skew/shear composition.
- Correct transform order matching FH6's editor math.
- Edge cases where a group is resized, rotated, skewed, then nested inside another transformed group.

Observed symptom before the translation patch:

- Ungrouped and nested exports had the same layer order, shape types, colors, scale, and rotation.
- Nested export coordinates were consistently local/off-center compared with the ungrouped export.
- This strongly indicated missing parent-group transform application rather than wrong layer decoding.

Current expectation:

- Flat/ungrouped export should remain safe.
- Grouped/nested export should be considered experimental until full affine parent transform composition is verified with side-by-side exports.

## Import Safety

Import is stricter than export because it writes into the game.

Current import requirements should remain:

- Fresh live editor group/table must be located immediately before writing.
- The selected table must validate every layer pointer needed for the write.
- Template count/vector metadata must be exact enough for culling/trimming.
- Stale fallback candidates should be refused.
- Cached addresses must not be reused across editor refreshes.

Flattened grouped export is read-only and can allow patterns that import must reject. Import should not use a flattened child-list candidate as a write target unless a future writer explicitly understands the parent group structure and write semantics.

## Export Safety

Export is read-only, but it still needs safety gates:

- Use only validated live `CLiveryGroup` candidates.
- Refuse candidates that do not look like normal editable/user-owned work.
- Keep the existing community/locked-work refusal behavior.
- Do not downgrade validation just to make small groups easier to find.

The latest fast-session export report path is important because the export validator previously expected only fallback probe reports. Fast RTTI sessions now need to carry enough validation metadata for export refusal/approval to work without requiring an old fallback report file.

## Current Implementation Notes

Relevant code locations:

- `fh6_probe.py`
  - `FH6_CALIBRATED_RTTI_PROFILE`
  - `locate_calibrated_clivery_group_rtti`
  - calibrated RTTI count scan
  - calibrated flattened-group scan
  - session metadata fields: `validated_entries`, `vtable`, `flattened_from_groups`, `flattened_group_count`, `flattened_max_depth`

- `fh6_export_typecode_json.py`
  - fast-session validation support
  - `collect_export_layer_pointers`
  - recursive grouped/nested flattening
  - current translation-only parent transform handling

- `tools/fh6-rtti-calibrator`
  - read-only workflow for rebuilding RTTI offsets after FH6 updates

- `tools/fh6-research-dumper`
  - compact dump tool for grouped/ungrouped/nested external reports

## Recommended Next Work

1. Finish full parent transform composition for grouped/nested export.
2. Validate full transform math by exporting the same design ungrouped and grouped/nested, then comparing every layer after normalization.
3. Keep import and export locators unified where possible, but keep write-safety stricter than read-safety.
4. Add small-count regression tests from captured dumps: 5, 6, 10, 14, 26, 41, 123, 231.
5. Keep the RTTI calibrator available as the recovery path after FH6 updates.
6. Document a user-facing "why export may refuse" explanation separately from this research doc.

## Open Questions

- What is the exact FH6 parent transform order for grouped layers?
- Are group transform fields always at the same offsets as layer transform fields?
- Are there special flags that change how grouped scale/skew are applied?
- Can import into grouped/nested structures ever be safe, or should import always target a flat reusable template?
- Can the RTTI path be adapted cleanly for FH5 via the game profile switch without weakening FH6 safety?
