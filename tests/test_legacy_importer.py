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
from legacy_importer import _pointer, import_legacy_package


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


    def test_normalized_view_projects_sparse_fields_and_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("0.1", "0.2", "0.3", "0.4"):
                with self.subTest(version=version):
                    target = pathlib.Path(tmp) / f"normalized-{version}.motionpack"
                    fixture = self._fixture(version)
                    with zipfile.ZipFile(fixture, "r") as source:
                        members = {
                            info.filename: source.read(info)
                            for info in source.infolist()
                            if not info.is_dir()
                        }
                    if version == "0.4":
                        manifest = json.loads(members["manifest.json"].decode("utf-8"))
                        manifest["nodes"][0]["interaction"] = {"hover": True}
                        members["manifest.json"] = json.dumps(
                            manifest, separators=(",", ":"), ensure_ascii=False
                        ).encode("utf-8")
                    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as output:
                        for member, payload in members.items():
                            output.writestr(member, payload)
                    snapshot = import_legacy_package(target, timeout=20)
                    normalized = snapshot.normalized
                    self.assertEqual(normalized.source_version, version)
                    self.assertEqual(normalized.manifest_bytes, snapshot.manifest_bytes)
                    self.assertEqual(normalized.entries, snapshot.entries)
                    self.assertEqual(normalized.assets, snapshot.assets)
                    self.assertEqual(
                        [node.node_id for node in normalized.nodes],
                        [node["id"] for node in snapshot.manifest["nodes"]],
                    )
                    for index, (node, raw_node) in enumerate(zip(
                        normalized.nodes, snapshot.manifest["nodes"]
                    )):
                        self.assertEqual(node.source_pointer, f"/nodes/{index}")
                        self.assertEqual(node.present_fields, frozenset(raw_node))
                        self.assertEqual(node.asset_field_present, "asset" in raw_node)
                        self.assertEqual(node.parent_field_present, "parent" in raw_node)
                        if "asset" in raw_node:
                            self.assertIs(node.asset, snapshot.assets[raw_node["asset"]])
                    self.assertEqual(set(normalized.clips), set(snapshot.manifest["clips"]))
                    for name, raw_clip in snapshot.manifest["clips"].items():
                        clip = normalized.clips[name]
                        self.assertEqual(clip.source_pointer, f"/clips/{name}")
                        self.assertEqual(clip.present_fields, frozenset(raw_clip))
                        self.assertEqual(clip.loop_present, "loop" in raw_clip)
                        self.assertEqual(
                            clip.loop_value, raw_clip.get("loop") if "loop" in raw_clip else None
                        )
                        self.assertEqual(len(clip.tracks), len(raw_clip.get("tracks", [])))
                        for index, track in enumerate(clip.tracks):
                            self.assertEqual(
                                track.source_pointer,
                                f"/clips/{name}/tracks/{index}",
                            )
                            self.assertEqual(
                                track.present_fields,
                                frozenset(raw_clip["tracks"][index]),
                            )
                    self.assertEqual(
                        normalized.defaults_present, "defaults" in snapshot.manifest
                    )
                    self.assertEqual(
                        normalized.canvas_source_pointer,
                        "/canvas" if "canvas" in snapshot.manifest else None,
                    )
                    self.assertEqual(
                        normalized.defaults_source_pointer,
                        "/defaults" if "defaults" in snapshot.manifest else None,
                    )
                    self.assertEqual(_pointer("clip/name~1"), "/clip~1name~01")
                    with self.assertRaises(TypeError):
                        normalized.clips["injected"] = None
                    if normalized.nodes:
                        with self.assertRaises(TypeError):
                            normalized.nodes[0].fields["injected"] = True
                    for clip in normalized.clips.values():
                        if clip.tracks:
                            with self.assertRaises(TypeError):
                                clip.tracks[0].values["injected"] = True
                    for variant in normalized.variants.values():
                        with self.assertRaises(TypeError):
                            variant.node_overrides["injected"] = None
                    if version == "0.4":
                        self.assertTrue(any(
                            "interaction" in node.fields for node in normalized.nodes
                        ))
                        self.assertTrue(any(
                            fact.identifier == "org.motionpack.interaction"
                            for fact in normalized.capability_facts
                        ))

    def test_v01_ik_is_normalized_with_spec_mismatch_diagnostic(self):
        source_path = self._fixture("0.2")
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "v01-with-ik.motionpack"
            with zipfile.ZipFile(source_path, "r") as source:
                members = {
                    info.filename: source.read(info)
                    for info in source.infolist()
                    if not info.is_dir()
                }
            manifest = json.loads(members["manifest.json"].decode("utf-8"))
            manifest["version"] = "0.1"
            members["manifest.json"] = json.dumps(
                manifest, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as output:
                for name, payload in members.items():
                    output.writestr(name, payload)

            before = hashlib.sha256(target.read_bytes()).digest()
            snapshot = import_legacy_package(target, timeout=20)
            self.assertEqual(hashlib.sha256(target.read_bytes()).digest(), before)
            self.assertEqual(snapshot.source_version, "0.1")
            self.assertEqual(snapshot.normalized.manifest_bytes, members["manifest.json"])
            self.assertTrue(snapshot.normalized.ik_chains)
            self.assertIn("org.motionpack.ik.two-bone", snapshot.capabilities)
            fact = next(
                item for item in snapshot.normalized.capability_facts
                if item.identifier == "org.motionpack.ik.two-bone"
            )
            self.assertEqual(
                fact.interpretation, "observed-with-version-spec-mismatch"
            )
            self.assertIn("/iks", fact.source_pointers)
            self.assertTrue(fact.diagnostic)
            self.assertIn(fact.diagnostic, snapshot.report.diagnostics)
            self.assertIn(fact.diagnostic, snapshot.normalized.diagnostics)


if __name__ == "__main__":
    unittest.main()
