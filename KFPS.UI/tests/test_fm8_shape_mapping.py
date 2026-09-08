from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fh6_export_typecode_json import annotate_fm_export_resource
from fh6_import_typecode_json import load_shapes
from tools.cgroup.cgroup_codec import CGroupLayer, build_flat_payload, layer_from_shape
from tools.cgroup.forza_source_decoder import decode_forza_source
from tools.cgroup.shape_identity import (
    canonical_shape_identity,
    fm8_resource_for_word,
    normalize_game_shape_word,
    target_game_shape_word,
)


# Independent expected native IDs, verified with all four in-game community grids.
COMMUNITY_BASES = (2101, 2201, 2301, 2401)

# Frozen tab identities from the 1,400-shape validation, not the production map.
LIBRARY_TABS = (
    ("Primitives", 101),
    ("Community_Vinyls_1", 2101), ("Community_Vinyls_2", 2201),
    ("Community_Vinyls_3", 2301), ("Community_Vinyls_4", 2401),
    ("Gradient_Shapes", 201), ("Stripes", 301), ("Tears", 401),
    ("Racing_Icons", 501), ("Flames", 601), ("Paint_Splats", 701),
    ("Tribal", 801), ("Nature", 901),
    ("Upper_Letters_1", 1901), ("Lower_Letters_1", 2001),
    ("Upper_Letters_2", 1301), ("Lower_Letters_2", 1401),
    ("Upper_Letters_3", 1501), ("Lower_Letters_3", 1601),
    ("Upper_Letters_4", 1701), ("Lower_Letters_4", 1801),
    ("Upper_Letters_5", 2501), ("Lower_Letters_5", 2601),
    ("Upper_Letters_6", 2701), ("Lower_Letters_6", 2801),
    ("Upper_Letters_7", 2901), ("Lower_Letters_7", 3001),
    ("Upper_Letters_8", 3101), ("Lower_Letters_8", 3201),
    ("Upper_Letters_9", 3301), ("Lower_Letters_9", 3401),
    ("Upper_Letters_10", 3501), ("Lower_Letters_10", 3601),
    ("Upper_Letters_11", 3701), ("Lower_Letters_11", 3801),
)


def grid_shape(word, index, *, metadata=False):
    shape = {
        "type": 0x100000 + word,
        "type_word": word,
        "data": [float(index * 8), float(-index * 4), 0.5, 0.75, 0, 0, 0],
        "color": [12, 34, 56, 255],
        "mask": False,
    }
    if metadata:
        shape.update(resource_family=f"Community_Vinyls_{word // 100 - 20}",
                     resource_index=word % 100)
    return shape


def library_shapes(*, metadata):
    shapes = []
    for family, base in LIBRARY_TABS:
        for index in range(40):
            shape = grid_shape(base + index, len(shapes))
            shape["mask"] = index % 2 == 0
            shape["data"][6] = int(shape["mask"])
            if metadata:
                shape.update(resource_family=family, resource_index=index + 1)
            shapes.append(shape)
    return shapes


class FM8ShapeMappingTests(unittest.TestCase):
    def test_full_library_import_preparation_preserves_all_1400_expected_ids(self):
        expected = [base + index for _, base in LIBRARY_TABS for index in range(40)]
        self.assertEqual(1400, len(set(expected)))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "all-shapes.json"
            for metadata in (False, True):
                shapes = library_shapes(metadata=metadata)
                path.write_text(json.dumps({"shapes": shapes}), encoding="utf-8")
                for game in ("fm", "fh4", "fh5", "fh6"):
                    with self.subTest(game=game, metadata=metadata):
                        prepared, skipped = load_shapes(
                            path, allow_unknown_low_byte=True, target_game=game
                        )
                        self.assertEqual([], skipped)
                        self.assertEqual(expected, [shape["shape_word"] for shape in prepared])
                        self.assertEqual([shape["data"][0] for shape in shapes],
                                         [shape["x"] for shape in prepared])

    def test_full_library_file_round_trip_preserves_ids_and_artwork(self):
        for metadata in (False, True):
            with self.subTest(metadata=metadata), tempfile.TemporaryDirectory() as temp:
                shapes = library_shapes(metadata=metadata)
                layers = [layer_from_shape(shape, i, target_game="fm8")
                          for i, shape in enumerate(shapes)]
                expected = [shape["type_word"] for shape in shapes]
                self.assertEqual(1400, len(layers))
                self.assertEqual(expected, [layer.shape_id for layer in layers])
                path = Path(temp) / "data"
                path.write_bytes(build_flat_payload(layers))
                decoded = decode_forza_source(path, allow_locked=False, game="fm8")
                self.assertEqual(expected, [shape["type_word"] for shape in decoded.layers])
                for source, actual in zip(shapes, decoded.layers):
                    self.assertEqual(source["data"][:6], actual["data"][:6])
                    self.assertEqual(source["color"], actual["color"])
                    self.assertEqual(source["mask"], actual["mask"])

    def test_all_community_raw_ids_export_as_the_same_canonical_identity(self):
        for tab, base in enumerate(COMMUNITY_BASES, 1):
            for index in range(1, 41):
                word = base + index - 1
                with self.subTest(tab=tab, index=index):
                    expected = (f"Community_Vinyls_{tab}", index)
                    self.assertEqual(expected, fm8_resource_for_word(word))
                    normalized = normalize_game_shape_word(word, "fm8")
                    self.assertEqual(word, normalized["canonical_word"])
                    self.assertEqual(word, normalized["raw_word"])

    def test_live_annotation_matches_native_ids_and_preserves_artwork_fields(self):
        for tab, base in enumerate(COMMUNITY_BASES, 1):
            for index in range(1, 41):
                word = base + index - 1
                with self.subTest(tab=tab, index=index):
                    shape = grid_shape(word, index)
                    shape["mask"] = index % 2 == 0
                    shape["data"][6] = int(shape["mask"])
                    before = copy.deepcopy(shape)
                    layer = {"type_word": word, "type_code": shape["type"]}
                    self.assertTrue(annotate_fm_export_resource(shape, layer, "fm"))
                    self.assertEqual(word, shape["type_word"])
                    self.assertEqual(0x100000 + word, shape["type"])
                    self.assertEqual((f"Community_Vinyls_{tab}", index),
                                     (shape["resource_family"], shape["resource_index"]))
                    self.assertEqual(word, layer["fm_raw_type_word"])
                    for field in ("data", "color", "mask"):
                        self.assertEqual(before[field], shape[field])

    def test_import_preparation_matches_with_or_without_resource_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "grid.json"
            for base in COMMUNITY_BASES:
                for metadata in (False, True):
                    with self.subTest(base=base, metadata=metadata):
                        shapes = [grid_shape(base + i, i, metadata=metadata) for i in range(40)]
                        path.write_text(json.dumps({"shapes": shapes}), encoding="utf-8")
                        prepared, skipped = load_shapes(path, allow_unknown_low_byte=True, target_game="fm")
                        self.assertEqual([], skipped)
                        self.assertEqual(list(range(base, base + 40)),
                                         [shape["shape_word"] for shape in prepared])
                        self.assertEqual([item["data"][0] for item in shapes],
                                         [item["x"] for item in prepared])

    def test_file_encoder_metadata_does_not_permute_community_words(self):
        for base in COMMUNITY_BASES:
            for index in range(40):
                word = base + index
                with self.subTest(word=word):
                    shape = grid_shape(word, index, metadata=True)
                    encoded = layer_from_shape(shape, index, target_game="fm8")
                    self.assertEqual(word, encoded.shape_id)

    def test_offline_decoder_preserves_all_160_community_ids(self):
        words = [base + index for base in COMMUNITY_BASES for index in range(40)]
        layers = [CGroupLayer(word, float(i), -float(i), 0.5, 0.75, 0, 0,
                              (12, 34, 56, 255), mask=i % 2 == 0)
                  for i, word in enumerate(words)]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data"
            path.write_bytes(build_flat_payload(layers))
            decoded = decode_forza_source(path, allow_locked=False, game="fm8")
        self.assertEqual(words, [shape["source_raw_type_word"] for shape in decoded.layers])
        self.assertEqual(words, [shape["type_word"] for shape in decoded.layers])
        for expected, actual in zip(layers, decoded.layers):
            self.assertEqual(expected.mask, actual["mask"])
            self.assertEqual(list(expected.color_rgba), actual["color"])
            self.assertEqual([expected.x, expected.y], actual["data"][:2])

    def test_compact_families_keep_their_existing_mapping(self):
        families = ("Primitives", "Gradient_Shapes", "Stripes", "Tears", "Racing_Icons",
                    "Flames", "Paint_Splats", "Tribal", "Nature")
        for tab, family in enumerate(families, 1):
            for index in range(1, 41):
                word = tab * 100 + index
                with self.subTest(family=family, index=index):
                    self.assertEqual((family, index), fm8_resource_for_word(word))
                    shape = {"resource_family": family, "resource_index": index}
                    self.assertEqual(word, target_game_shape_word(shape, word, "fm8"))
                    live = grid_shape(word, index)
                    self.assertTrue(annotate_fm_export_resource(live, {}, "fm"))
                    self.assertEqual(word, live["type_word"])

    def test_same_game_raw_provenance_and_horizon_imports_remain_unchanged(self):
        shape = grid_shape(2112, 0, metadata=True)
        shape.update(source_game="fm8", source_raw_type_word=2117)
        identity = canonical_shape_identity(shape)
        self.assertEqual(2117, target_game_shape_word(shape, identity.word, "fm8"))
        for game in ("fh4", "fh5", "fh6"):
            with self.subTest(game=game):
                self.assertEqual(2112, target_game_shape_word(shape, identity.word, game))
                before = copy.deepcopy(shape)
                self.assertFalse(annotate_fm_export_resource(shape, {}, game))
                self.assertEqual(before, shape)

    def test_camelcase_resource_metadata_uses_the_same_native_identity(self):
        shape = {"type_word": 2117, "resourceFamily": "Community_Vinyls_1", "resourceIndex": "17"}
        self.assertEqual(2117, target_game_shape_word(shape, 2117, "fm"))

    def test_unknown_and_noncommunity_words_are_not_reinterpreted(self):
        for word in (0, 100, 141, 2041, 2100, 2141, 2441, 3101, 65535):
            with self.subTest(word=word):
                self.assertIsNone(fm8_resource_for_word(word))
                shape = grid_shape(word, 0)
                before = copy.deepcopy(shape)
                self.assertFalse(annotate_fm_export_resource(shape, {}, "fm"))
                self.assertEqual(before, shape)


if __name__ == "__main__":
    unittest.main()
