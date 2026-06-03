# FH6 Locator Dump Findings - 2026-06-03

Source dataset: `Deckers Vinyl Data` memory captures.

## Coverage

- 23 unique captures reviewed.
- 18 captures had clean exact candidates under the original strict rules.
- 20 captures are usable after distinguishing export-safe table reads from import-safe editable vectors.
- 3 captures remain correctly refused because no full layer-pointer table candidate was present.

## State Coverage

- Ungrouped: 498, 1966, 1999, 2804, 3000 layers.
- Grouped: 26, 498, 1926, 1966, 2804, 3000, 3000 layers.
- Grouped groups / nested groups: 26, 41, 123, 125, 509, 686, 899, 1926 usable; 720, 1122, 2066 partial only.

## Important Behavior

Grouped-groups can expose a full readable layer pointer table while the group vector end describes only a smaller child range. This pattern is export-safe when:

- requested count matches the group count field,
- the table has the requested number of readable pointers,
- invalid pointer count is zero,
- at least a small validation sample decodes,
- table capacity covers the requested layer count.

That same pattern is not import/trim-safe. Import still requires a fresh template with exact vector metadata because trimming writes the group count/vector end.

## Locator Rules

Candidate priority is now:

1. Full table, zero invalid pointers, all sampled/decoded layers valid.
2. Full table, zero invalid pointers, enough decoded layers.
3. Higher valid pointer count.
4. Higher decoded layer count.
5. Fewer invalid pointers.
6. Exact vector metadata as a tie-breaker.
7. Probe score as final tie-breaker.

Shape mix is no longer allowed to outrank exact table structure. The old circle/square-heavy score could put partial nested-group candidates ahead of exact candidates.

## Safety Split

Import:

- Requires exact vector metadata.
- Requires full pointer table.
- Requires fresh circle-template check.
- Still trims after writing.

Export:

- Requires full pointer table.
- Allows grouped-groups where vector end is smaller than the requested count.
- Does not write to the game.
- The selected group/table must be present in the probe report.

## Refused Captures

These were partial and should remain refused unless future research finds a reliable parent/child aggregation method:

- `20260603-180038_2066_grouped_groups_2066layers`
- `20260603-184142_1122_grouped_groups_1122layers`
- `20260603-194934_720_grouped_groups_720layers`
