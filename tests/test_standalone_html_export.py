"""Offline HTML exporter tests against actual v0.x packages."""
import pathlib
import tempfile
import unittest
import zipfile

from tools.export_html import export_html
from tools.package import build

ROOT = pathlib.Path(__file__).resolve().parent.parent


class StandaloneHTMLExportTests(unittest.TestCase):
    def test_export_reuses_the_exact_reference_preview(self):
        for example in ("robot_ik_demo", "interaction_demo"):
            with self.subTest(example=example), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                archive, preview = build(ROOT / "examples" / example, root / "built")
                dest = root / "playable.html"
                self.assertEqual(export_html(archive, dest), dest)
                self.assertEqual(dest.read_bytes(), preview.read_bytes())
                self.assertIn(b"window.MotionPackPlayer", dest.read_bytes())

    def test_export_does_not_leak_optional_source_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            archive, _ = build(ROOT / "examples" / "robot_demo", root / "built")
            with zipfile.ZipFile(archive, mode="a") as writer:
                writer.writestr("source/private.txt", "PRIVATE_SOURCE_SENTINEL_8U4")
            dest = root / "playable.html"
            export_html(archive, dest)
            self.assertNotIn(b"PRIVATE_SOURCE_SENTINEL_8U4", dest.read_bytes())

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            archive, _ = build(ROOT / "examples" / "robot_demo", root / "built")
            dest = root / "playable.html"
            dest.write_text("original", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                export_html(archive, dest)
            self.assertEqual(dest.read_text(encoding="utf-8"), "original")

    def test_corrupt_zip_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            archive = root / "bad.motionpack"
            archive.write_bytes(b"not a ZIP")
            dest = root / "playable.html"
            with self.assertRaises(ValueError):
                export_html(archive, dest)
            self.assertFalse(dest.exists())

    def test_repeat_exports_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            archive, _ = build(ROOT / "examples" / "robot_demo", root / "built")
            a, b = root / "first.html", root / "second.html"
            export_html(archive, a)
            export_html(archive, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())


if __name__ == "__main__":
    unittest.main()
