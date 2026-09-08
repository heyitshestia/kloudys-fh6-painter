# FM8 Community Shape Identity

FM8's community picker order is not the canonical resource index. A picker
position must not be used to translate a native layer word into another identity.

Manual Steam FM8 validation covered all 40 shapes in each of the four community
tabs. Explicit-ID imports, refreshed game screenshots and saved-file captures
confirmed native ranges 2101-2140, 2201-2240, 2301-2340 and 2401-2440 match the
canonical resources. The old picker permutation changed 39, 39, 37 and 36 IDs.

## Implementation

- `tools/cgroup/shape_identity.py` owns the canonical community mapping.
- The live exporter's `FM_EXPORT_RESOURCE_MAP` references that shared map instead
  of maintaining a separate 160-entry picker-order table.
- Live import preparation and the file encoder use the same native identity for
  explicit IDs and equivalent community resource metadata.
- Compact/legacy non-community mappings and same-game raw provenance are unchanged.
- Locator discovery, validation and ownership policy are unchanged.

## Existing Files

New live exports and offline Library scans use the corrected identities. A Library
rescan can replace an old generated JSON in place from its original saved source;
deleting the cache or changing the game save is not required.

Arbitrary previously exported or downloaded JSON files are not automatically
rewritten. Their history may include either wrong export conversion or an earlier
wrong import, and two inverse errors can hide in a successful JSON round trip.
Prefer a fresh export from the intended in-game design. Existing trustworthy
same-game raw provenance is still honored, not stripped or guessed.

## Validation Boundaries

Regression tests cover all 160 community IDs through import preparation, live
annotation, file encoding and offline decoding, plus non-community compatibility
and rescanning an existing Library entry. Saved-file replay confirms corrected IDs
without changing source data. Game screenshots establish visible identity; a
JSON-only round trip is insufficient.

An independent 35-tab regression fixture also covers all 1,400 expected identities
through FM8/FH4/FH5/FH6 import preparation, both with and without resource metadata,
and through the FM8 file encoder/decoder while retaining artwork fields.

Manual full-library validation on Steam FM8 imported all 1,400 shapes, matched the
pre-save live export, and matched the actual saved-file export without changing
the source save. Exported IDs, transforms, colours and masks all matched. Enlarged
screenshots directly verified 800 identities (all 520 non-font shapes and 280
glyphs); the user confirmed the remaining 600 glyphs looked correct. These are
separate evidence levels, not a claim that every glyph was reference-compared.

The post-save live capture was refused by the unchanged ownership verification;
saved persistence was verified from the actual saved file instead. Separate raw-ID
report annotations cover 520 non-font shapes; 880 font annotations are unavailable.
Neither gap is hidden by the matching exported records or visual confirmation.

This result supports the community-only correction, not a library-wide remap or
compatibility proof for every FM8 build/store variant. The manual grid and screenshots
are private test material, not bundled user artwork. Library thumbnails can simplify
gradient/texture shading; exact rendering fidelity and intermittent locator refusals
remain separate issues, not corrected by an identity-map change.
