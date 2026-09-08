from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
from kfps_ui.background_remove_document import MaskDocument, paint_mask


class DocumentTests(unittest.TestCase):
    def make(self, root):
        run = root / "run"
        run.mkdir()
        image = Image.new("RGBA", (100,80), (220,0,0,255))
        image.paste("white", (10,10,80,70))
        image.putpixel((20,20), (255,255,255,0))
        image.save(run / "source.png")
        result = image.copy()
        result.paste((220,0,0,0), (0,0,5,80))
        result.save(root / "output.png")
        return MaskDocument.create(run, root/"output.png", root/"my original.png")

    def test_stroke_undo_redo_reopen_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = self.make(root)
            before = doc.current().tobytes()
            self.assertTrue(doc.edit("erase", [[.4,.4],[.6,.6]], 12))
            erased = doc.current().tobytes()
            self.assertNotEqual(before, erased)
            self.assertTrue(doc.can_undo)
            doc = MaskDocument.open(doc.run)
            self.assertEqual(erased, doc.current().tobytes())
            self.assertTrue(doc.step(-1))
            self.assertEqual(before, doc.current().tobytes())
            self.assertTrue(doc.step(1))
            self.assertEqual(erased, doc.current().tobytes())
            target = doc.export(root / "exports")
            with Image.open(target) as image:
                self.assertEqual(erased, image.tobytes())

    def test_restore_does_not_reveal_original_hidden_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self.make(Path(tmp))
            doc.edit("erase", [[.2,.25]], 30)
            doc.edit("restore", [[.2,.25]], 30)
            self.assertEqual(0, doc.current().getpixel((20,20))[3])
            self.assertEqual(255, doc.current().getpixel((22,22))[3])

    def test_area_eraser_removes_connected_color_not_separate_foreground(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self.make(Path(tmp))
            doc.edit("wand", [[.95,.5]], tolerance=0)
            self.assertEqual(0, doc.current().getpixel((95,40))[3])
            self.assertEqual(255, doc.current().getpixel((40,40))[3])

    def test_reset_is_undoable_and_new_stroke_discards_redo(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self.make(Path(tmp))
            before = doc.current().tobytes()
            doc.edit("erase", [[.5,.5]], 20)
            erased = doc.current().tobytes()
            doc.reset()
            self.assertEqual(before, doc.current().tobytes())
            doc.step(-1)
            self.assertEqual(erased, doc.current().tobytes())
            doc.edit("erase", [[.3,.3]], 10)
            self.assertFalse(doc.can_redo)

    def test_save_failure_keeps_previous_state_and_no_half_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self.make(Path(tmp))
            before = doc.current().tobytes()
            entries = list(doc.folder.iterdir())
            with patch("kfps_ui.background_remove_document.atomic_json", side_effect=PermissionError("disk locked")):
                with self.assertRaises(PermissionError):
                    doc.edit("erase", [[.4,.4]], 10)
            self.assertEqual(before, doc.current().tobytes())
            self.assertEqual(entries, list(doc.folder.iterdir()))
            self.assertEqual(before, MaskDocument.open(doc.run).current().tobytes())

    def test_original_and_revision_corruption_rejected(self):
        for filename in ("source", "current"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as tmp:
                doc = self.make(Path(tmp))
                path = doc.run/"source.png" if filename == "source" else doc.current_path
                path.write_bytes(b"corrupted")
                with self.assertRaises(ValueError):
                    MaskDocument.open(doc.run)

    def test_corrupt_pointer_cannot_read_outside_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self.make(Path(tmp))
            state = doc.state.copy()
            state["entries"][0]["file"] = "../../private.png"
            doc.path.write_text(json.dumps(state))
            with self.assertRaises(ValueError):
                MaskDocument.open(doc.run)

    def test_bounded_history_preserves_original_and_latest(self):
        with tempfile.TemporaryDirectory() as tmp, patch("kfps_ui.background_remove_document.MAX_ENTRIES", 4):
            doc = self.make(Path(tmp))
            base = doc.current().tobytes()
            for x in (.2,.3,.4,.5,.6,.7):
                doc.edit("erase", [[x,.5]], 5)
            self.assertEqual(4, len(doc.state["entries"]))
            self.assertEqual(4, len(list(doc.folder.glob("revision-*.png"))))
            doc.reset()
            self.assertEqual(base, doc.current().tobytes())

    def test_invalid_strokes_never_change_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self.make(Path(tmp))
            before = doc.current().tobytes()
            for points in ([], [[float("nan"),.5]], [[-1,.5]], [[1.01,.5]], [[True,.5]], [[.1]], [[.5,.5]]*4097):
                with self.subTest(points=str(points)[:40]), self.assertRaises(ValueError):
                    doc.edit("erase", points)
            for diameter in (0,-1,1001,float("nan"),True):
                with self.assertRaises(ValueError):
                    doc.edit("erase", [[.5,.5]], diameter)
            self.assertEqual(before, doc.current().tobytes())

    def test_no_change_does_not_allocate_a_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = self.make(Path(tmp))
            self.assertFalse(doc.edit("erase", [[0,.5]], 1))
            self.assertEqual(1, len(doc.state["entries"]))

    def test_repeated_strokes_maintain_canvas_contract(self):
        original = Image.new("RGBA", (80,60), "white")
        current = original.copy()
        for index in range(5):
            current = paint_mask(original, current, "erase", [[.3+index*.1,.5]], 10)
        self.assertEqual(original.size, current.size)
        self.assertTrue(np.all(np.asarray(current.getchannel("A")) <= 255))


if __name__ == "__main__":
    unittest.main()
