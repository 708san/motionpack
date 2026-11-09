import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from archive_reader import ArchiveError, ReaderLimits
from legacy_importer import import_legacy_package


class LegacyImporterTests(unittest.TestCase):
    def _fixture(self, version):
        folder = "fuzz_corpus/archive_reader" if version in ("0.1", "0.2") else "fixtures/compatibility_archive_reader"
        return ROOT / "tests" / folder / f"valid_v{version.replace('.', '')}.motionpack"

    def test_read_only_snapshots_preserve_all_v01_to_v04_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("0.1", "0.2", "0.3", "0.4"):
                with self.subTest(version=version):
                    original = self._fixture(version)
                    target = pathlib.Path(tmp) / f"extended-{version}.motionpack"
                    expected = {}
                    with zipfile.ZipFile(original, "r") as source:
                        for info in source.infolist():
                            if info.is_dir():
                                continue
                            expected[info.filename] = source.read(info)
                    manifest = json.loads(expected["manifest.json"].decode("utf-8"))
                    manifest["futureTopLevelField"] = {"opaque": [1, "two"]}
                    if version == "0.4":
                        manifest["nodes"][0]["interaction"] = {"hover": True}
                    expected["manifest.json"] = json.dumps(
                        manifest, separators=(",", ":"), ensure_ascii=False
                    ).encode("utf-8")
                    opaque_source = bytes((0x50, 0x4B, 0x03, 0x04, 0x00)) + b"arbitrary source bytes"
                    expected["source/original.bin"] = opaque_source
                    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as output:
                        for name, payload in expected.items():
                            output.writestr(name, payload)

                    before_digest = hashlib.sha256(target.read_bytes()).digest()
                    snapshot = import_legacy_package(target, timeout=20)
                    self.assertEqual(hashlib.sha256(target.read_bytes()).digest(), before_digest)
                    if version == "0.1":
                        with self.assertRaises(ArchiveError):
                            import_legacy_package(
                                target, limits=ReaderLimits(max_total_uncompressed=1), timeout=20
                            )
                        self.assertEqual(hashlib.sha256(target.read_bytes()).digest(), before_digest)
                    self.assertEqual(snapshot.source_version, version)
                    self.assertEqual(snapshot.manifest_bytes, expected["manifest.json"])
                    self.assertEqual(snapshot.entries, expected)
                    self.assertEqual(snapshot.source_entries, {"source/original.bin": opaque_source})
                    with self.assertRaises(TypeError):
                        snapshot.entries["source/new.bin"] = b"changed"
                    with self.assertRaises(TypeError):
                        snapshot.manifest["id"] = "changed"
                    with self.assertRaises(TypeError):
                        snapshot.manifest["nodes"][0]["id"] = "changed"
                    known_fields = {"format", "version", "id", "canvas", "assets", "nodes", "clips", "variants", "defaults", "iks"}
                    self.assertEqual(
                        snapshot.report.unrecognized_manifest_fields,
                        tuple(sorted(set(manifest) - known_fields)),
                    )
                    self.assertEqual(
                        set(snapshot.assets),
                        set(snapshot.manifest["assets"]),
                    )
                    for asset_id, imported_asset in snapshot.assets.items():
                        self.assertEqual(imported_asset.asset_id, asset_id)
                        self.assertEqual(imported_asset.path, snapshot.manifest["assets"][asset_id])
                        self.assertEqual(imported_asset.data, expected[imported_asset.path])
                    if version == "0.2":
                        self.assertIn("org.motionpack.ik.two-bone", snapshot.capabilities)
                    if version == "0.4":
                        self.assertIn("org.motionpack.interaction", snapshot.capabilities)
                    else:
                        self.assertNotIn("org.motionpack.interaction", snapshot.capabilities)
                    if version in ("0.3", "0.4"):
                        self.assertEqual(
                            snapshot.validation_profiles,
                            ("org.motionpack.validation.svg-dimensions-v0.3",),
                        )
                    else:
                        self.assertEqual(snapshot.validation_profiles, ())


if __name__ == "__main__":
    unittest.main()
