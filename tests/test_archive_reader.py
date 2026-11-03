import json
import io
import pathlib
import shutil
import stat
import struct
import sys
import tempfile
import warnings
import unittest
import zipfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import archive_reader
from archive_reader import ArchiveError, ReaderLimits, read_package
from package import build


class NonSeekableBuffer(io.BytesIO):
    def seekable(self):
        return False

    def seek(self, *args):
        raise io.UnsupportedOperation("not seekable")


class ArchiveReaderTests(unittest.TestCase):
    def _package(self, folder, out):
        archive, _ = build(folder, out)
        return archive

    def _zip(self, path, entries, *, compression=zipfile.ZIP_STORED):
        with zipfile.ZipFile(path, "w", compression=compression) as archive:
            for name, data in entries:
                archive.writestr(name, data)
        return path

    def test_reads_existing_v01_and_v02_packages(self):
        for project, version in (("robot_demo", "0.1"), ("robot_ik_demo", "0.2")):
            with self.subTest(project=project), tempfile.TemporaryDirectory() as tmp:
                archive = self._package(ROOT / "examples" / project, pathlib.Path(tmp) / "out")
                package = read_package(archive)
                self.assertEqual(package.manifest["version"], version)
                self.assertEqual(set(package.assets), set(package.manifest["assets"]))
                self.assertTrue(all(package.assets.values()))

    def test_untrusted_svg_is_rejected_through_archive_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "out")
            with zipfile.ZipFile(packed) as original:
                manifest = json.loads(original.read("manifest.json"))
                target = next(iter(manifest["assets"].values()))
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            entries = [(name, b'<!DOCTYPE svg [<!ENTITY x "boom">]><svg xmlns="http://www.w3.org/2000/svg"/>' if name == target else data) for name, data in entries]
            unsafe = self._zip(pathlib.Path(tmp) / "unsafe-svg.motionpack", entries)
            with self.assertRaisesRegex(ArchiveError, "invalid package manifest or assets"):
                read_package(unsafe)

    def test_reads_zip_with_leading_stub_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = self._package(ROOT / "examples" / "robot_demo", pathlib.Path(tmp) / "build")
            prefixed = pathlib.Path(tmp) / "prefixed.motionpack"
            prefixed.write_bytes(b"MOTIONPACK-STUB-DATA" + package.read_bytes())
            result = read_package(prefixed)
            self.assertEqual(result.manifest["version"], "0.1")

    def test_source_entries_are_not_read_or_extracted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = ROOT / "examples" / "robot_ik_demo"
            archive = self._package(project, pathlib.Path(tmp) / "out")
            entries = []
            with zipfile.ZipFile(archive) as original:
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            entries.append(("source/private.txt", b"private source bytes"))
            source_archive = self._zip(pathlib.Path(tmp) / "with-source.motionpack", entries)
            package = read_package(source_archive)
            self.assertEqual(set(package.assets), set(package.manifest["assets"]))

    def test_manifest_cannot_expose_source_as_runtime_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "out")
            with zipfile.ZipFile(archive) as original:
                manifest = json.loads(original.read("manifest.json"))
                entries = [(item.filename, original.read(item)) for item in original.infolist()]
            manifest["assets"]["source_probe"] = "source/private.svg"
            entries = [(name, json.dumps(manifest).encode() if name == "manifest.json" else data) for name, data in entries]
            entries.append(("source/private.svg", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"))
            source_archive = self._zip(pathlib.Path(tmp) / "referenced-source.motionpack", entries)
            with self.assertRaisesRegex(ArchiveError, "source entries"):
                read_package(source_archive)

    def test_rejects_unsafe_names_before_returning_assets(self):
        unsafe_names = ("../escape", "/absolute", "C:/drive", "\\\\server\\share", "assets\\x.svg", "assets//x.svg", "assets/./x.svg")
        for name in unsafe_names:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                archive = self._zip(pathlib.Path(tmp) / "bad.motionpack", [(name, b"x"), ("manifest.json", b"{}")])
                with self.assertRaises(ArchiveError):
                    read_package(archive)

    def test_rejects_duplicate_and_casefold_colliding_names(self):
        fixtures = (
            [("manifest.json", b"{}"), ("manifest.json", b"{}")],
            [("manifest.json", b"{}"), ("Assets/a.svg", b"a"), ("assets/A.svg", b"b")],
            [("manifest.json", b"{}"), ("assets/\u00e9.svg", b"a"), ("assets/e\u0301.svg", b"b")],
        )
        for entries in fixtures:
            with self.subTest(entries=[name for name, _ in entries]), tempfile.TemporaryDirectory() as tmp:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    archive = self._zip(pathlib.Path(tmp) / "collision.motionpack", entries)
                with self.assertRaises(ArchiveError):
                    read_package(archive)

    def test_rejects_symlink_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "symlink.motionpack"
            info = zipfile.ZipInfo("assets/link.svg")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("manifest.json", b"{}")
                archive.writestr(info, "../../outside")
            with self.assertRaisesRegex(ArchiveError, "symlink"):
                read_package(path)

    def test_entry_and_expanded_size_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "many.motionpack", [("manifest.json", b"{}"), ("extra", b"x")])
            with self.assertRaisesRegex(ArchiveError, "entry count"):
                read_package(path, limits=ReaderLimits(max_entries=1))
            with self.assertRaisesRegex(ArchiveError, "expanded size"):
                read_package(path, limits=ReaderLimits(max_total_uncompressed=2))

    def test_entry_count_is_checked_before_zipfile_parses_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "too-many.motionpack", [("manifest.json", b"{}"), ("extra", b"x")])
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "entry count"):
                    read_package(path, limits=ReaderLimits(max_entries=1))
                zip_file.assert_not_called()

    def test_central_directory_limit_and_count_mismatch_precede_zipfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "directory-limit.motionpack", [("manifest.json", b"{}")])
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "central directory"):
                    read_package(path, limits=ReaderLimits(max_central_directory_bytes=1))
                zip_file.assert_not_called()

            data = bytearray(path.read_bytes())
            end = data.rfind(b"PK\x05\x06")
            data[end + 8:end + 12] = struct.pack("<HH", 0, 0)
            path.write_bytes(data)
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "entry count"):
                    read_package(path)
                zip_file.assert_not_called()

    def test_rejects_zip64_locator_and_eocd_signature_in_comment_before_zipfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "locator.motionpack", [("manifest.json", b"{}")])
            data = path.read_bytes()
            end = data.rfind(b"PK\x05\x06")
            path.write_bytes(data[:end] + b"PK\x06\x07" + b"\0" * 16 + data[end:])
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaisesRegex(ArchiveError, "ZIP64"):
                    read_package(path)
                zip_file.assert_not_called()

            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("manifest.json", b"{}")
                archive.comment = b"PK\x05\x06"
            with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                with self.assertRaises(ArchiveError):
                    read_package(path)
                zip_file.assert_not_called()

    def test_rejects_zip64_local_extra_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "zip64-local.motionpack"
            with zipfile.ZipFile(path, "w") as archive:
                with archive.open("manifest.json", "w", force_zip64=True) as manifest:
                    manifest.write(b"{}")
            with self.assertRaisesRegex(ArchiveError, "ZIP64"):
                read_package(path)

    def test_accepts_valid_data_descriptors(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            buffer = NonSeekableBuffer()
            with zipfile.ZipFile(original) as source, zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target:
                for info in source.infolist():
                    with target.open(info.filename, "w") as member:
                        member.write(source.read(info))
            path = pathlib.Path(tmp) / "descriptor.motionpack"
            path.write_bytes(buffer.getvalue())
            result = read_package(path)
            self.assertEqual(result.manifest["version"], "0.2")

    def test_rejects_local_crc_or_size_mismatch(self):
        for offset in (14, 18, 22):
            with self.subTest(offset=offset), tempfile.TemporaryDirectory() as tmp:
                path = self._zip(pathlib.Path(tmp) / "bad-local.motionpack", [("manifest.json", b"{}")])
                data = bytearray(path.read_bytes())
                data[offset] ^= 0x01
                path.write_bytes(data)
                with mock.patch.object(archive_reader.zipfile, "ZipFile") as zip_file:
                    with self.assertRaisesRegex(ArchiveError, "CRC/size"):
                        read_package(path)
                    zip_file.assert_not_called()

    def test_aggregate_limit_counts_unique_zip_assets_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_copy = pathlib.Path(tmp) / "project"
            shutil.copytree(ROOT / "examples" / "robot_ik_demo", project_copy)
            manifest_path = project_copy / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assets"]["background_alias"] = manifest["assets"]["background"]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            path = self._package(project_copy, pathlib.Path(tmp) / "build")
            with zipfile.ZipFile(path) as archive:
                unique_asset_paths = set(json.loads(archive.read("manifest.json"))["assets"].values())
                asset_total = sum(archive.getinfo(name).file_size for name in unique_asset_paths)
            result = read_package(path, limits=ReaderLimits(max_total_assets_bytes=asset_total))
            self.assertEqual(result.assets["background_alias"], result.assets["background"])

    def test_total_asset_limit_is_checked_before_asset_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with self.assertRaisesRegex(ArchiveError, "declared total asset size"):
                read_package(path, limits=ReaderLimits(max_total_assets_bytes=1))

    def test_rejects_excessive_compression_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = b"A" * 8192
            path = self._zip(pathlib.Path(tmp) / "ratio.motionpack", [("manifest.json", b"{}"), ("extra", data)], compression=zipfile.ZIP_DEFLATED)
            with self.assertRaisesRegex(ArchiveError, "compression ratio"):
                read_package(path, limits=ReaderLimits(max_compression_ratio=2))

    def test_rejects_nested_archive_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._zip(pathlib.Path(tmp) / "nested.motionpack", [("manifest.json", b"{}"), ("extras/nested.zip", b"PK\x03\x04")])
            with self.assertRaisesRegex(ArchiveError, "nested archive"):
                read_package(path)

    def test_rejects_invalid_reader_limits(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            ReaderLimits(max_entries=0)
        with self.assertRaisesRegex(ValueError, "finite"):
            ReaderLimits(max_compression_ratio=float("inf"))

    def test_missing_or_invalid_manifest_is_rejected(self):
        for entries in ([("assets/a.svg", b"x")], [("manifest.json", b"not json")]):
            with self.subTest(entries=entries), tempfile.TemporaryDirectory() as tmp:
                path = self._zip(pathlib.Path(tmp) / "invalid.motionpack", entries)
                with self.assertRaises(ArchiveError):
                    read_package(path)

    def test_rejects_duplicate_json_keys_and_missing_referenced_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            duplicate = self._zip(
                pathlib.Path(tmp) / "duplicate-json.motionpack",
                [("manifest.json", b'{"format":"motionpack","assets":{},"assets":{}}')],
            )
            with self.assertRaisesRegex(ArchiveError, "invalid package manifest"):
                read_package(duplicate)

            valid = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with zipfile.ZipFile(valid) as package:
                manifest = json.loads(package.read("manifest.json"))
                omitted = next(iter(manifest["assets"].values()))
                entries = [(item.filename, package.read(item)) for item in package.infolist() if item.filename != omitted]
            missing = self._zip(pathlib.Path(tmp) / "missing-asset.motionpack", entries)
            with self.assertRaisesRegex(ArchiveError, "missing archive asset"):
                read_package(missing)

    def test_manifest_and_asset_read_limits_are_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            with self.assertRaisesRegex(ArchiveError, "manifest size"):
                read_package(path, limits=ReaderLimits(max_manifest_bytes=1))
            with self.assertRaisesRegex(ArchiveError, "asset size"):
                read_package(path, limits=ReaderLimits(max_asset_bytes=1))

    def test_rejects_truncated_or_non_zip_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "not-a-zip.motionpack"
            path.write_bytes(b"not a ZIP archive")
            with self.assertRaises(ArchiveError):
                read_package(path)

            valid = self._package(ROOT / "examples" / "robot_ik_demo", pathlib.Path(tmp) / "build")
            truncated = pathlib.Path(tmp) / "truncated.motionpack"
            truncated.write_bytes(valid.read_bytes()[:-24])
            with self.assertRaises(ArchiveError):
                read_package(truncated)

    def test_corrupt_deflate_stream_uses_archive_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "corrupt-deflate.motionpack"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", b'{"format":"motionpack"}')
            with zipfile.ZipFile(path) as archive:
                info = archive.getinfo("manifest.json")
                offset = info.header_offset
            data = bytearray(path.read_bytes())
            filename_length, extra_length = struct.unpack_from("<HH", data, offset + 26)
            compressed_data_offset = offset + 30 + filename_length + extra_length
            data[compressed_data_offset] ^= 0xFF
            path.write_bytes(data)
            with self.assertRaisesRegex(ArchiveError, "unable to read manifest"):
                read_package(path)

    def test_does_not_create_files_outside_archive_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            outside = root / "escape"
            archive = self._zip(root / "slip.motionpack", [("../escape", b"owned"), ("manifest.json", b"{}")])
            with self.assertRaises(ArchiveError):
                read_package(archive)
            self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
