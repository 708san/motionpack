import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile
from dataclasses import FrozenInstanceError

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from archive_reader import ArchiveError, ReaderLimits
from legacy_importer import ImportReport, LegacyImportSnapshot, _pointer, import_legacy_package


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
                    manifest["nodes"][0]["futureNestedField"] = {"opaque": "nested"}
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
                    findings = snapshot.report.migration_findings
                    canvas_mapping = next(
                        item for item in findings
                        if item.source_pointer == "/canvas"
                    )
                    self.assertEqual(canvas_mapping.disposition, "confirmed_mapping")
                    self.assertEqual(canvas_mapping.normalized_target, "canvas")
                    self.assertEqual(
                        canvas_mapping.scope, "experimental-normalized-view"
                    )
                    root_targets = {
                        "version": "source_version",
                        "id": "identifier",
                        "canvas": "canvas",
                        "assets": "assets",
                        "nodes": "nodes",
                        "clips": "clips",
                        "variants": "variants",
                        "defaults": "defaults",
                        "iks": "ik_chains",
                    }
                    expected_mappings = {
                        _pointer(field): target
                        for field, target in root_targets.items()
                        if field in manifest
                        and not (
                            field == "iks"
                            and version == "0.1"
                            and manifest["iks"]
                        )
                    }
                    actual_mappings = {
                        item.source_pointer: item.normalized_target
                        for item in findings
                        if item.disposition == "confirmed_mapping"
                    }
                    self.assertEqual(actual_mappings, expected_mappings)
                    unsupported = next(
                        item for item in findings
                        if item.source_pointer == "/futureTopLevelField"
                    )
                    self.assertEqual(unsupported.disposition, "unsupported")
                    self.assertIsNone(unsupported.normalized_target)
                    self.assertIn("preserves this field", unsupported.reason)
                    self.assertEqual(
                        snapshot.manifest["futureTopLevelField"]["opaque"],
                        (1, "two"),
                    )
                    nested_node = snapshot.normalized.nodes[0]
                    self.assertEqual(
                        nested_node.fields["futureNestedField"]["opaque"], "nested"
                    )
                    self.assertFalse(any(
                        item.source_pointer
                        == _pointer("nodes", 0, "futureNestedField")
                        for item in findings
                    ))
                    with self.assertRaises(FrozenInstanceError):
                        canvas_mapping.disposition = "unsupported"
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


    def test_omitted_loop_default_is_separate_and_has_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("0.1", "0.2", "0.3", "0.4"):
                with self.subTest(version=version):
                    source = self._fixture(version)
                    target = pathlib.Path(tmp) / f"loop-default-{version}.motionpack"
                    with zipfile.ZipFile(source, "r") as archive:
                        members = {
                            info.filename: archive.read(info)
                            for info in archive.infolist()
                            if not info.is_dir()
                        }
                    manifest = json.loads(members["manifest.json"].decode("utf-8"))
                    clip_names = list(manifest["clips"])
                    self.assertTrue(clip_names)
                    while len(clip_names) < 3:
                        probe_name = f"loop_default_probe_{len(clip_names)}"
                        manifest["clips"][probe_name] = json.loads(
                            json.dumps(manifest["clips"][clip_names[0]])
                        )
                        clip_names.append(probe_name)
                    manifest["clips"][clip_names[0]]["loop"] = True
                    manifest["clips"][clip_names[1]]["loop"] = False
                    for name in clip_names[2:]:
                        manifest["clips"][name].pop("loop", None)
                    members["manifest.json"] = json.dumps(
                        manifest, separators=(",", ":"), ensure_ascii=False
                    ).encode("utf-8")
                    with zipfile.ZipFile(
                        target, "w", compression=zipfile.ZIP_DEFLATED
                    ) as archive:
                        for name, payload in members.items():
                            archive.writestr(name, payload)

                    before_digest = hashlib.sha256(target.read_bytes()).digest()
                    snapshot = import_legacy_package(target, timeout=20)
                    self.assertEqual(
                        hashlib.sha256(target.read_bytes()).digest(), before_digest
                    )

                    normalized = snapshot.normalized
                    self.assertEqual(snapshot.source_version, version)
                    authored_true = normalized.clips[clip_names[0]]
                    authored_false = normalized.clips[clip_names[1]]
                    self.assertTrue(authored_true.loop_present)
                    self.assertTrue(authored_true.loop_value)
                    self.assertTrue(authored_false.loop_present)
                    self.assertFalse(authored_false.loop_value)
                    self.assertNotIn(
                        authored_true.source_pointer + "/loop",
                        normalized.effective_defaults,
                    )
                    self.assertNotIn(
                        authored_false.source_pointer + "/loop",
                        normalized.effective_defaults,
                    )
                    actual_loop_defaults = {
                        pointer
                        for pointer in normalized.effective_defaults
                        if pointer.startswith("/clips/") and pointer.endswith("/loop")
                    }
                    self.assertEqual(
                        actual_loop_defaults,
                        {f"/clips/{name}/loop" for name in clip_names[2:]},
                    )
                    for name in clip_names[2:]:
                        pointer = f"/clips/{name}/loop"
                        effective = normalized.effective_defaults[pointer]
                        self.assertFalse(normalized.clips[name].loop_present)
                        self.assertIsNone(normalized.clips[name].loop_value)
                        self.assertFalse(effective.value)
                        self.assertEqual(effective.source_version, version)
                        self.assertEqual(effective.source_pointer, pointer)
                        self.assertFalse(effective.field_present)
                        self.assertEqual(
                            effective.rule_id,
                            "motionpack.v0.clip.loop.default-false",
                        )
                        self.assertEqual(effective.rule_origin, "format-spec")
                        with self.assertRaises(FrozenInstanceError):
                            effective.value = True
                    with self.assertRaises(TypeError):
                        normalized.effective_defaults["/clips/injected/loop"] = None

    def test_burst_count_default_is_version_gated_and_implementation_sourced(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("0.1", "0.2", "0.3", "0.4"):
                with self.subTest(version=version):
                    source = self._fixture(version)
                    target = pathlib.Path(tmp) / f"burst-count-{version}.motionpack"
                    with zipfile.ZipFile(source, "r") as archive:
                        members = {
                            info.filename: archive.read(info)
                            for info in archive.infolist()
                            if not info.is_dir()
                        }
                    manifest = json.loads(members["manifest.json"].decode("utf-8"))
                    clip_name = "burst_default_probe"
                    base_clip = next(iter(manifest["clips"].values()))
                    probe = json.loads(json.dumps(base_clip))
                    duration = probe["duration_ms"]
                    node_id = manifest["nodes"][0]["id"]
                    probe["effects"] = [
                        {
                            "kind": "burst",
                            "node": node_id,
                            "start_ms": 0,
                            "duration_ms": duration,
                        },
                        {
                            "kind": "burst",
                            "node": node_id,
                            "start_ms": 0,
                            "duration_ms": duration,
                            "count": 0,
                        },
                        {
                            "kind": "burst",
                            "node": node_id,
                            "start_ms": 0,
                            "duration_ms": duration,
                            "count": 9,
                        },
                    ]
                    manifest["clips"][clip_name] = probe
                    members["manifest.json"] = json.dumps(
                        manifest, separators=(",", ":"), ensure_ascii=False
                    ).encode("utf-8")
                    with zipfile.ZipFile(
                        target, "w", compression=zipfile.ZIP_DEFLATED
                    ) as archive:
                        for name, payload in members.items():
                            archive.writestr(name, payload)

                    before_digest = hashlib.sha256(target.read_bytes()).digest()
                    snapshot = import_legacy_package(target, timeout=20)
                    self.assertEqual(
                        hashlib.sha256(target.read_bytes()).digest(), before_digest
                    )
                    self.assertEqual(snapshot.source_version, version)
                    normalized_clip = snapshot.normalized.clips[clip_name]
                    self.assertEqual(len(normalized_clip.effects), 3)

                    omitted = normalized_clip.effects[0]
                    omitted_pointer = _pointer(
                        "clips", clip_name, "effects", 0, "count"
                    )
                    self.assertNotIn("count", omitted.present_fields)
                    self.assertNotIn("count", omitted.values)
                    effective = snapshot.normalized.effective_defaults[omitted_pointer]
                    self.assertEqual(effective.value, 28)
                    self.assertEqual(effective.source_version, version)
                    self.assertEqual(effective.source_pointer, omitted_pointer)
                    self.assertFalse(effective.field_present)
                    self.assertEqual(
                        effective.rule_id,
                        "motionpack.v0.effect.burst.count.default-28",
                    )
                    self.assertEqual(effective.rule_origin, "implementation")
                    with self.assertRaises(FrozenInstanceError):
                        effective.value = 1

                    for index, authored_count in ((1, 0), (2, 9)):
                        effect = normalized_clip.effects[index]
                        pointer = _pointer(
                            "clips", clip_name, "effects", index, "count"
                        )
                        self.assertIn("count", effect.present_fields)
                        self.assertEqual(effect.values["count"], authored_count)
                        self.assertNotIn(
                            pointer, snapshot.normalized.effective_defaults
                        )
                    with self.assertRaises(TypeError):
                        snapshot.normalized.effective_defaults[
                            "/clips/injected/effects/0/count"
                        ] = None

    def test_ik_weight_default_is_version_gated_and_has_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("0.1", "0.2", "0.3", "0.4"):
                source_version = "0.2" if version == "0.1" else version
                source = self._fixture(source_version)
                with zipfile.ZipFile(source, "r") as archive:
                    source_members = {
                        info.filename: archive.read(info)
                        for info in archive.infolist()
                        if not info.is_dir()
                    }

                for authored_weight in (None, 0.25):
                    with self.subTest(version=version, authored_weight=authored_weight):
                        target = pathlib.Path(tmp) / (
                            f"ik-weight-{version}-{authored_weight}.motionpack"
                        )
                        members = dict(source_members)
                        manifest = json.loads(members["manifest.json"].decode("utf-8"))
                        manifest["version"] = version
                        if version in ("0.3", "0.4"):
                            manifest["nodes"].extend([
                                {"id": "ik_upper_test", "x": 0, "y": 0, "z": 10},
                                {
                                    "id": "ik_lower_test",
                                    "parent": "ik_upper_test",
                                    "x": 10,
                                    "y": 0,
                                    "z": 11,
                                },
                            ])
                            manifest["iks"] = [{
                                "id": "ik_weight_test",
                                "upper": "ik_upper_test",
                                "lower": "ik_lower_test",
                                "lengths": [10, 10],
                                "target": [15, 0],
                                "bend": -1,
                            }]
                        chain = manifest["iks"][0]
                        if authored_weight is None:
                            chain.pop("weight", None)
                        else:
                            chain["weight"] = authored_weight
                        members["manifest.json"] = json.dumps(
                            manifest, separators=(",", ":"), ensure_ascii=False
                        ).encode("utf-8")
                        with zipfile.ZipFile(
                            target, "w", compression=zipfile.ZIP_DEFLATED
                        ) as archive:
                            for name, payload in members.items():
                                archive.writestr(name, payload)

                        before_digest = hashlib.sha256(target.read_bytes()).digest()
                        snapshot = import_legacy_package(target, timeout=20)
                        self.assertEqual(
                            hashlib.sha256(target.read_bytes()).digest(),
                            before_digest,
                        )
                        self.assertEqual(snapshot.source_version, version)
                        normalized = snapshot.normalized
                        pointer = "/iks/0/weight"
                        if authored_weight is not None:
                            self.assertIn(
                                "weight", normalized.ik_chains[0].present_fields
                            )
                            self.assertEqual(
                                normalized.ik_chains[0].values["weight"],
                                authored_weight,
                            )
                            self.assertNotIn(pointer, normalized.effective_defaults)
                        else:
                            self.assertNotIn(
                                "weight", normalized.ik_chains[0].present_fields
                            )
                            self.assertNotIn("weight", normalized.ik_chains[0].values)
                            if version == "0.1":
                                self.assertNotIn(pointer, normalized.effective_defaults)
                                self.assertTrue(any(
                                    fact.identifier == "org.motionpack.ik.two-bone"
                                    and fact.interpretation
                                    == "observed-with-version-spec-mismatch"
                                    for fact in normalized.capability_facts
                                ))
                            else:
                                effective = normalized.effective_defaults[pointer]
                                self.assertEqual(effective.value, 1)
                                self.assertEqual(effective.source_version, version)
                                self.assertEqual(effective.source_pointer, pointer)
                                self.assertFalse(effective.field_present)
                                self.assertEqual(
                                    effective.rule_id,
                                    "motionpack.v0.2.ik.weight.default-one",
                                )
                                self.assertEqual(
                                    effective.rule_origin, "format-spec"
                                )

    def test_ik_bend_default_is_version_gated_and_implementation_sourced(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("0.2", "0.3", "0.4"):
                source = self._fixture(version)
                with zipfile.ZipFile(source, "r") as archive:
                    source_members = {
                        info.filename: archive.read(info)
                        for info in archive.infolist()
                        if not info.is_dir()
                    }

                for authored_bend in (None, -1):
                    with self.subTest(version=version, authored_bend=authored_bend):
                        target = pathlib.Path(tmp) / (
                            f"ik-bend-{version}-{authored_bend}.motionpack"
                        )
                        members = dict(source_members)
                        manifest = json.loads(
                            members["manifest.json"].decode("utf-8")
                        )
                        if version in ("0.3", "0.4"):
                            manifest["nodes"].extend([
                                {"id": "ik_bend_upper_test", "x": 0, "y": 0, "z": 10},
                                {
                                    "id": "ik_bend_lower_test",
                                    "parent": "ik_bend_upper_test",
                                    "x": 10,
                                    "y": 0,
                                    "z": 11,
                                },
                            ])
                            manifest["iks"] = [{
                                "id": "ik_bend_test",
                                "upper": "ik_bend_upper_test",
                                "lower": "ik_bend_lower_test",
                                "lengths": [10, 10],
                                "target": [15, 0],
                            }]
                        chain = manifest["iks"][0]
                        if authored_bend is None:
                            chain.pop("bend", None)
                        else:
                            chain["bend"] = authored_bend
                        members["manifest.json"] = json.dumps(
                            manifest, separators=(",", ":"), ensure_ascii=False
                        ).encode("utf-8")
                        with zipfile.ZipFile(
                            target, "w", compression=zipfile.ZIP_DEFLATED
                        ) as archive:
                            for name, payload in members.items():
                                archive.writestr(name, payload)

                        before_digest = hashlib.sha256(target.read_bytes()).digest()
                        snapshot = import_legacy_package(target, timeout=20)
                        self.assertEqual(
                            hashlib.sha256(target.read_bytes()).digest(),
                            before_digest,
                        )
                        self.assertEqual(snapshot.source_version, version)
                        pointer = "/iks/0/bend"
                        normalized_chain = snapshot.normalized.ik_chains[0]
                        if authored_bend is None:
                            self.assertNotIn("bend", normalized_chain.present_fields)
                            self.assertNotIn("bend", normalized_chain.values)
                            effective = snapshot.normalized.effective_defaults[pointer]
                            self.assertEqual(effective.value, 1)
                            self.assertEqual(effective.source_version, version)
                            self.assertEqual(effective.source_pointer, pointer)
                            self.assertFalse(effective.field_present)
                            self.assertEqual(
                                effective.rule_id,
                                "motionpack.v0.2.ik.bend.default-one",
                            )
                            self.assertEqual(effective.rule_origin, "implementation")
                        else:
                            self.assertIn("bend", normalized_chain.present_fields)
                            self.assertEqual(
                                normalized_chain.values["bend"], authored_bend
                            )
                            self.assertNotIn(
                                pointer, snapshot.normalized.effective_defaults
                            )

    def test_v04_interaction_defaults_are_version_gated_and_provenanced(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "interaction-defaults.motionpack"
            source = self._fixture("0.4")
            with zipfile.ZipFile(source, "r") as archive:
                members = {
                    info.filename: archive.read(info)
                    for info in archive.infolist()
                    if not info.is_dir()
                }
            manifest = json.loads(members["manifest.json"].decode("utf-8"))
            manifest["nodes"][0]["interaction"] = {
                "hover": True,
                "click": False,
            }
            manifest["nodes"][1].pop("interaction", None)
            members["manifest.json"] = json.dumps(
                manifest, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            with zipfile.ZipFile(
                target, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for name, payload in members.items():
                    archive.writestr(name, payload)

            before_digest = hashlib.sha256(target.read_bytes()).digest()
            snapshot = import_legacy_package(target, timeout=20)
            self.assertEqual(
                hashlib.sha256(target.read_bytes()).digest(), before_digest
            )
            normalized = snapshot.normalized
            self.assertEqual(snapshot.source_version, "0.4")

            expected_pointers = set()
            for index, node in enumerate(manifest["nodes"]):
                flags = node.get("interaction", {})
                for flag in ("hover", "tap", "click"):
                    pointer = f"/nodes/{index}/interaction/{flag}"
                    if flag not in flags:
                        expected_pointers.add(pointer)
                        effective = normalized.effective_defaults[pointer]
                        self.assertFalse(effective.value)
                        self.assertEqual(effective.source_version, "0.4")
                        self.assertEqual(effective.source_pointer, pointer)
                        self.assertFalse(effective.field_present)
                        self.assertEqual(
                            effective.rule_id,
                            "motionpack.v0.4.interaction.flag.default-disabled",
                        )
                        self.assertEqual(effective.rule_origin, "format-spec")
                    else:
                        self.assertNotIn(pointer, normalized.effective_defaults)
            actual_node_defaults = {
                pointer
                for pointer in normalized.effective_defaults
                if pointer.startswith("/nodes/")
            }
            self.assertEqual(actual_node_defaults, expected_pointers)
            self.assertEqual(
                normalized.nodes[0].fields["interaction"]["hover"], True
            )
            self.assertEqual(
                normalized.nodes[0].fields["interaction"]["click"], False
            )
            with self.assertRaises(TypeError):
                normalized.effective_defaults["/nodes/injected/interaction/tap"] = None

            for version in ("0.1", "0.2", "0.3"):
                with self.subTest(version=version):
                    legacy = import_legacy_package(
                        self._fixture(version), timeout=20
                    )
                    self.assertFalse(any(
                        pointer.startswith("/nodes/")
                        for pointer in legacy.normalized.effective_defaults
                    ))

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
                    self.assertIs(normalized.manifest, snapshot.manifest)
                    if "canvas" in snapshot.manifest:
                        self.assertIs(normalized.canvas, snapshot.manifest["canvas"])
                    if "defaults" in snapshot.manifest:
                        self.assertIs(normalized.defaults, snapshot.manifest["defaults"])
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

    def test_legacy_snapshot_constructor_remains_compatible(self):
        report = ImportReport((), 0, 0, (), ())
        snapshot = LegacyImportSnapshot(
            "0.1", {}, b"{}", {}, {}, (), (), report
        )
        self.assertIsNone(snapshot.normalized)

    def test_report_source_facts_are_deterministic_and_source_only(self):
        for version in ("0.1", "0.2", "0.3", "0.4"):
            with self.subTest(version=version):
                source = self._fixture(version)
                before = hashlib.sha256(source.read_bytes()).digest()
                first = import_legacy_package(source, timeout=20)
                second = import_legacy_package(source, timeout=20)
                self.assertEqual(
                    hashlib.sha256(source.read_bytes()).digest(), before
                )
                facts = first.report.source_facts
                self.assertEqual(facts, second.report.source_facts)
                self.assertEqual(
                    first.report.migration_findings,
                    second.report.migration_findings,
                )
                version_fact = next(
                    fact for fact in facts
                    if fact.category == "source-format-version"
                )
                self.assertEqual(version_fact.source_version, version)
                self.assertEqual(version_fact.identifier, "motionpack.format")
                self.assertEqual(version_fact.source_pointers, ("/version",))
                self.assertFalse(hasattr(version_fact, "target_capability"))

                profile_facts = [
                    fact for fact in facts
                    if fact.category == "validation-profile"
                ]
                if version in ("0.3", "0.4"):
                    self.assertEqual(len(profile_facts), 1)
                    self.assertEqual(
                        profile_facts[0].identifier,
                        "org.motionpack.validation.svg-dimensions-v0.3",
                    )
                    self.assertEqual(
                        profile_facts[0].source_pointers, ("/version",)
                    )
                else:
                    self.assertEqual(profile_facts, [])

                if version == "0.4":
                    self.assertTrue(any(
                        fact.category == "observed-declaration"
                        and fact.identifier == "org.motionpack.interaction"
                        and fact.source_pointers[0].startswith("/nodes/")
                        for fact in facts
                    ))

                with self.assertRaises(FrozenInstanceError):
                    version_fact.category = "v1-required-capability"
                self.assertIsInstance(version_fact.source_pointers, tuple)

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
            manifest["iks"][0].pop("bend", None)
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
            self.assertNotIn("bend", snapshot.normalized.ik_chains[0].present_fields)
            self.assertNotIn("bend", snapshot.normalized.ik_chains[0].values)
            self.assertNotIn(
                "/iks/0/bend", snapshot.normalized.effective_defaults
            )
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
            source_fact = next(
                item for item in snapshot.report.source_facts
                if item.category == "observed-construct"
                and item.identifier == "org.motionpack.ik.two-bone"
            )
            self.assertEqual(source_fact.source_version, "0.1")
            self.assertIn("/iks", source_fact.source_pointers)
            self.assertIn("v1 meaning is unresolved", source_fact.diagnostic)
            self.assertFalse(hasattr(source_fact, "target_capability"))
            ambiguous = next(
                item for item in snapshot.report.migration_findings
                if item.source_pointer == "/iks"
            )
            self.assertEqual(ambiguous.disposition, "preserved_uninterpreted")
            self.assertIsNone(ambiguous.normalized_target)
            self.assertEqual(ambiguous.scope, "v1-semantics")
            self.assertIn("no v1 semantic meaning", ambiguous.reason.lower())
            self.assertEqual(ambiguous.source_field, "iks")
            self.assertFalse(any(
                item.source_pointer == "/iks"
                and item.disposition == "confirmed_mapping"
                for item in snapshot.report.migration_findings
            ))
            expected_ik_track_pointers = {
                _pointer("clips", clip_name, "ik_tracks")
                for clip_name, clip in manifest["clips"].items()
                if clip.get("ik_tracks")
            }
            self.assertGreaterEqual(len(expected_ik_track_pointers), 2)
            ik_track_findings = [
                item for item in snapshot.report.migration_findings
                if item.source_field == "ik_tracks"
            ]
            self.assertEqual(
                {item.source_pointer for item in ik_track_findings},
                expected_ik_track_pointers,
            )
            for item in ik_track_findings:
                self.assertEqual(item.disposition, "preserved_uninterpreted")
                self.assertIsNone(item.normalized_target)
                self.assertEqual(item.scope, "v1-semantics")

            empty_manifest = json.loads(members["manifest.json"].decode("utf-8"))
            empty_manifest["iks"] = []
            for clip in empty_manifest["clips"].values():
                clip.pop("ik_tracks", None)
            empty_members = dict(members)
            empty_members["manifest.json"] = json.dumps(
                empty_manifest, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            empty_target = pathlib.Path(tmp) / "v01-empty-iks.motionpack"
            with zipfile.ZipFile(
                empty_target, "w", compression=zipfile.ZIP_DEFLATED
            ) as output:
                for name, payload in empty_members.items():
                    output.writestr(name, payload)
            empty_snapshot = import_legacy_package(empty_target, timeout=20)
            empty_iks_finding = next(
                item for item in empty_snapshot.report.migration_findings
                if item.source_pointer == "/iks"
            )
            self.assertEqual(
                empty_iks_finding.disposition, "confirmed_mapping"
            )
            self.assertEqual(empty_iks_finding.normalized_target, "ik_chains")
            self.assertFalse(any(
                item.disposition == "preserved_uninterpreted"
                and item.source_field in ("iks", "ik_tracks")
                for item in empty_snapshot.report.migration_findings
            ))
            self.assertNotIn(
                "org.motionpack.ik.two-bone", empty_snapshot.capabilities
            )


if __name__ == "__main__":
    unittest.main()
