"""Bounded, read-only reader for experimental MotionPack ZIP packages.

This module validates archive metadata before reading the manifest or assets. It
never extracts ZIP members to a caller-controlled path and does not interpret
optional ``source/`` entries.
"""
from dataclasses import dataclass
import json
import math
import os
import pathlib
import re
import stat
import struct
import tempfile
from typing import Optional
import unicodedata
import zipfile
import zlib

try:
    from .validate import (
        MAX_ASSET, MAX_ASSETS, MAX_MANIFEST, MAX_PNG_DIMENSION, MAX_PNG_PIXELS,
        MAX_SVG_DIMENSION, MAX_SVG_PIXELS, MAX_TOTAL_ASSETS, MAX_TOTAL_PNG_PIXELS,
        PNG_SPEC_MAX_DIMENSION, check_json_nesting, validate,
    )
except ImportError:  # Support direct execution/import from the tools directory.
    from validate import (
        MAX_ASSET, MAX_ASSETS, MAX_MANIFEST, MAX_PNG_DIMENSION, MAX_PNG_PIXELS,
        MAX_SVG_DIMENSION, MAX_SVG_PIXELS, MAX_TOTAL_ASSETS, MAX_TOTAL_PNG_PIXELS,
        PNG_SPEC_MAX_DIMENSION, check_json_nesting, validate,
    )


class ArchiveError(ValueError):
    """The archive is malformed, unsupported, unsafe, or outside configured limits."""


@dataclass(frozen=True)
class ReaderLimits:
    """Resource ceilings for this reader; these are not format-wide guarantees."""

    max_archive_bytes: int = 40 * 1024 * 1024
    max_entries: int = 1024
    max_central_directory_bytes: int = 2 * 1024 * 1024
    max_manifest_bytes: int = MAX_MANIFEST
    max_asset_bytes: int = MAX_ASSET
    max_total_assets_bytes: int = MAX_TOTAL_ASSETS
    max_total_uncompressed: int = 40 * 1024 * 1024
    max_compression_ratio: float = 100.0
    max_png_dimension: int = MAX_PNG_DIMENSION
    max_png_pixels: int = MAX_PNG_PIXELS
    max_total_png_pixels: int = MAX_TOTAL_PNG_PIXELS
    max_raster_dimension: Optional[int] = None
    max_raster_pixels: Optional[int] = None
    max_total_raster_pixels: Optional[int] = None
    max_svg_dimension: int = MAX_SVG_DIMENSION
    max_svg_pixels: int = MAX_SVG_PIXELS

    def __post_init__(self):
        byte_limits = (
            self.max_archive_bytes,
            self.max_entries,
            self.max_central_directory_bytes,
            self.max_manifest_bytes,
            self.max_asset_bytes,
            self.max_total_assets_bytes,
            self.max_total_uncompressed,
        )
        if any(type(value) is not int or value <= 0 for value in byte_limits):
            raise ValueError("reader integer limits must be positive")
        png_limits = (self.max_png_dimension, self.max_png_pixels, self.max_total_png_pixels)
        if any(type(value) is not int or value <= 0 for value in png_limits):
            raise ValueError("reader PNG integer limits must be positive")
        if self.max_png_dimension > PNG_SPEC_MAX_DIMENSION:
            raise ValueError("reader PNG dimension limit exceeds PNG specification maximum")
        raster_limits = (self.max_raster_dimension, self.max_raster_pixels, self.max_total_raster_pixels)
        if any(value is not None and (type(value) is not int or value <= 0) for value in raster_limits):
            raise ValueError("reader raster integer limits must be positive")
        svg_limits = (self.max_svg_dimension, self.max_svg_pixels)
        svg_maxima = (MAX_SVG_DIMENSION, MAX_SVG_PIXELS)
        if any(type(value) is not int or value <= 0 or value > maximum
               for value, maximum in zip(svg_limits, svg_maxima)):
            raise ValueError("reader SVG limits must be positive and cannot exceed v0.3 maxima")
        if not isinstance(self.max_compression_ratio, (int, float)) or not math.isfinite(self.max_compression_ratio) or self.max_compression_ratio <= 0:
            raise ValueError("reader compression ratio limit must be finite and positive")


@dataclass(frozen=True)
class MotionPackArchive:
    """Validated manifest and its referenced image bytes, held in bounded memory."""

    manifest: dict
    assets: dict


def _error(message, cause=None):
    error = ArchiveError(message)
    if cause is None:
        raise error
    raise error from cause


def _member_parts(name):
    if not isinstance(name, str) or not name or "\x00" in name or "\\" in name:
        _error("unsafe archive entry name")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        _error("absolute archive entry path")
    path = name[:-1] if name.endswith("/") else name
    parts = path.split("/")
    if not path or any(part in ("", ".", "..") for part in parts):
        _error("unsafe archive entry path")
    if len(name) > 256:
        _error("archive entry path is too long")
    return parts


def _is_source_path(path):
    """Whether a normalized project path is inside the reserved source tree."""
    parts = pathlib.PurePosixPath(path).parts
    return bool(parts and parts[0].casefold() == "source")


def _preflight_end_record(stream, file_size, limits):
    """Validate classic ZIP directory structure before ZipFile parses it."""
    tail_size = min(file_size, 22 + 0xFFFF)
    stream.seek(file_size - tail_size)
    tail = stream.read(tail_size)
    marker = b"PK\x05\x06"
    position = tail.rfind(marker)
    if position < 0 or position + 22 > len(tail):
        _error("ZIP end record is missing or malformed")
    record = struct.unpack_from("<4s4H2LH", tail, position)
    comment_length = record[-1]
    if position + 22 + comment_length != len(tail):
        _error("ZIP end record comment is malformed")
    if position >= 20 and tail[position - 20:position - 16] == b"PK\x06\x07":
        _error("ZIP64 archives are unsupported")

    _, disk, directory_disk, disk_entries, entries, directory_size, directory_offset, _ = record
    if disk or directory_disk or disk_entries != entries:
        _error("multi-disk ZIP archives are unsupported")
    if entries == 0xFFFF or directory_size == 0xFFFFFFFF or directory_offset == 0xFFFFFFFF:
        _error("ZIP64 archives are unsupported")
    if entries > limits.max_entries:
        _error("archive entry count exceeds limit")
    if directory_size > limits.max_central_directory_bytes:
        _error("ZIP central directory exceeds limit")
    end_record_offset = file_size - tail_size + position
    concat = end_record_offset - (directory_offset + directory_size)
    if concat < 0:
        _error("ZIP central directory bounds are invalid")
    actual_directory_offset = directory_offset + concat

    stream.seek(actual_directory_offset)
    directory = stream.read(directory_size)
    if len(directory) != directory_size:
        _error("ZIP central directory is truncated")
    header = struct.Struct("<4s4B4HL2L5H2L")
    cursor = 0
    parsed_entries = 0
    while cursor < len(directory):
        if cursor + header.size > len(directory):
            _error("ZIP central directory record is truncated")
        fields = header.unpack_from(directory, cursor)
        if fields[0] != b"PK\x01\x02":
            _error("ZIP central directory record is invalid")
        compressed_size, uncompressed_size = fields[10], fields[11]
        filename_length, extra_length, entry_comment_length = fields[12:15]
        disk_start = fields[15]
        record_end = cursor + header.size + filename_length + extra_length + entry_comment_length
        if record_end > len(directory):
            _error("ZIP central directory record is truncated")
        if compressed_size == 0xFFFFFFFF or uncompressed_size == 0xFFFFFFFF or disk_start == 0xFFFF:
            _error("ZIP64 entries are unsupported")
        if disk_start:
            _error("multi-disk ZIP archives are unsupported")
        filename_start = cursor + header.size
        filename_bytes = directory[filename_start:filename_start + filename_length]
        extra_start = cursor + header.size + filename_length
        extra_end = extra_start + extra_length
        extra_cursor = extra_start
        while extra_cursor < extra_end:
            if extra_cursor + 4 > extra_end:
                _error("ZIP extra field is malformed")
            tag, size = struct.unpack_from("<HH", directory, extra_cursor)
            field_end = extra_cursor + 4 + size
            if field_end > extra_end:
                _error("ZIP extra field is malformed")
            if tag == 0x0001:
                _error("ZIP64 entries are unsupported")
            extra_cursor = field_end

        local_offset = fields[18] + concat
        stream.seek(local_offset)
        local_header = stream.read(30)
        local_struct = struct.Struct("<4s5H3L2H")
        if len(local_header) != local_struct.size:
            _error("ZIP local header is truncated")
        local_fields = local_struct.unpack(local_header)
        if local_fields[0] != b"PK\x03\x04":
            _error("ZIP local header is invalid")
        if local_fields[2] != fields[5] or local_fields[3] != fields[6]:
            _error("ZIP local and central metadata disagree")
        local_name_length, local_extra_length = local_fields[9:11]
        local_name = stream.read(local_name_length)
        local_extra = stream.read(local_extra_length)
        if local_name != filename_bytes or len(local_extra) != local_extra_length:
            _error("ZIP local and central names disagree")
        if local_fields[7] == 0xFFFFFFFF or local_fields[8] == 0xFFFFFFFF:
            _error("ZIP64 entries are unsupported")
        local_extra_cursor = 0
        while local_extra_cursor < len(local_extra):
            if local_extra_cursor + 4 > len(local_extra):
                _error("ZIP local extra field is malformed")
            tag, size = struct.unpack_from("<HH", local_extra, local_extra_cursor)
            field_end = local_extra_cursor + 4 + size
            if field_end > len(local_extra):
                _error("ZIP local extra field is malformed")
            if tag == 0x0001:
                _error("ZIP64 entries are unsupported")
            local_extra_cursor = field_end
        data_end = local_offset + local_struct.size + local_name_length + local_extra_length + compressed_size
        if data_end > actual_directory_offset:
            _error("ZIP entry data overlaps central directory")
        local_crc, local_compressed_size, local_uncompressed_size = local_fields[6:9]
        central_crc = fields[9]
        if fields[5] & 0x8:
            if local_crc not in (0, central_crc):
                _error("ZIP local and central CRC values disagree")
            if local_compressed_size not in (0, compressed_size):
                _error("ZIP local and central sizes disagree")
            if local_uncompressed_size not in (0, uncompressed_size):
                _error("ZIP local and central sizes disagree")
            descriptor_remaining = actual_directory_offset - data_end
            if descriptor_remaining < 12:
                _error("ZIP data descriptor is truncated")
            stream.seek(data_end)
            descriptor = stream.read(min(16, descriptor_remaining))
            expected_descriptor = (central_crc, compressed_size, uncompressed_size)
            descriptor_values = None
            descriptor_length = 12
            if descriptor[:4] == b"PK\x07\x08" and len(descriptor) >= 16:
                tagged_values = struct.unpack_from("<3L", descriptor, 4)
                if tagged_values == expected_descriptor:
                    descriptor_values = tagged_values
                    descriptor_length = 16
            unsigned_values = struct.unpack_from("<3L", descriptor) if len(descriptor) >= 12 else None
            if descriptor_values is None and unsigned_values == expected_descriptor:
                descriptor_values = unsigned_values
            if descriptor_values != expected_descriptor:
                _error("ZIP data descriptor disagrees with central directory")
            if data_end + descriptor_length > actual_directory_offset:
                _error("ZIP data descriptor overlaps central directory")
        elif (local_crc, local_compressed_size, local_uncompressed_size) != (central_crc, compressed_size, uncompressed_size):
            _error("ZIP local and central CRC/size values disagree")
        parsed_entries += 1
        if parsed_entries > limits.max_entries:
            _error("archive entry count exceeds limit")
        cursor = record_end
    if parsed_entries != entries or disk_entries != entries:
        _error("ZIP end record entry count does not match directory")


_ARCHIVE_PREFIXES = (
    b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08",  # ZIP
    b"\x1f\x8b",  # gzip
    b"\xfd7zXZ\x00",  # xz
    b"7z\xbc\xaf\x27\x1c",  # 7-Zip
    b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00",  # RAR
)
_ARCHIVE_PREFIX_BYTES = 512


def _looks_like_archive(data):
    if any(data.startswith(signature) for signature in _ARCHIVE_PREFIXES):
        return True
    # bzip2 requires a block-size digit after the three-byte "BZh" marker.
    if data.startswith(b"BZh") and len(data) >= 4 and data[3:4] in b"123456789":
        return True
    # tar has no fixed leading signature. Validate its header checksum to avoid
    # treating arbitrary files containing the word "ustar" as archives.
    if len(data) < _ARCHIVE_PREFIX_BYTES or data == b"\0" * _ARCHIVE_PREFIX_BYTES:
        return False
    checksum_field = data[148:156].strip(b"\0 ")
    try:
        expected = int(checksum_field, 8)
    except ValueError:
        return False
    header_sum = sum(data[:148]) + 8 * ord(" ") + sum(data[156:_ARCHIVE_PREFIX_BYTES])
    return header_sum == expected


def _bounded_prefix_read(archive, info, limit=_ARCHIVE_PREFIX_BYTES):
    """Read only a small decompressed prefix of an entry for format sniffing."""
    chunks = []
    remaining = limit
    try:
        with archive.open(info, "r") as member:
            while remaining:
                chunk = member.read(remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
    except (OSError, RuntimeError, EOFError, zipfile.BadZipFile, NotImplementedError, zlib.error) as exc:
        _error("unable to inspect archive entry", exc)
    return b"".join(chunks)


def _preflight(archive, limits):
    infos = archive.infolist()
    if len(infos) > limits.max_entries:
        _error("archive entry count exceeds limit")

    exact_names = set()
    normalized_names = {}
    portable_components = {}
    path_kinds = {}
    total_uncompressed = 0
    allowed_compression = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}

    for info in infos:
        name = info.filename
        parts = _member_parts(name)
        if not info.is_dir() and not _is_source_path(name) and pathlib.PurePosixPath(name).suffix.lower() in {
            ".zip", ".motionpack", ".tar", ".tgz", ".gz", ".bz2", ".xz", ".7z", ".rar",
        }:
            _error("nested archive entries are unsupported")
        if name in exact_names:
            _error("duplicate archive entry name")
        exact_names.add(name)

        normalized = unicodedata.normalize("NFC", name.rstrip("/"))
        folded = normalized.casefold()
        prior = normalized_names.get(folded)
        if prior is not None:
            _error("archive entry name collision")
        normalized_names[folded] = name

        # Reject component collisions too (for example A/x and a/y), so the
        # package has the same path tree on case-insensitive filesystems.
        for index, part in enumerate(parts):
            prefix = tuple(unicodedata.normalize("NFC", item).casefold() for item in parts[:index + 1])
            spelling = tuple(unicodedata.normalize("NFC", item) for item in parts[:index + 1])
            previous = portable_components.get(prefix)
            if previous is not None and previous != spelling:
                _error("archive path component collision")
            portable_components[prefix] = spelling

            kind = "directory" if index < len(parts) - 1 or info.is_dir() else "file"
            previous_kind = path_kinds.get(prefix)
            if previous_kind is not None and previous_kind != kind:
                _error("archive file/directory path collision")
            path_kinds[prefix] = kind

        if info.flag_bits & 0x1:
            _error("encrypted archive entries are unsupported")
        if info.compress_type not in allowed_compression:
            _error("unsupported archive compression method")
        if info.file_size < 0 or info.compress_size < 0:
            _error("invalid archive entry size")

        mode = info.external_attr >> 16
        file_type = stat.S_IFMT(mode)
        if file_type == stat.S_IFLNK:
            _error("symlink archive entries are forbidden")
        if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
            _error("special archive entries are forbidden")
        if info.is_dir() and file_type not in (0, stat.S_IFDIR):
            _error("archive entry type does not match its name")
        if not info.is_dir() and file_type == stat.S_IFDIR:
            _error("archive entry type does not match its name")

        total_uncompressed += info.file_size
        if info.file_size > limits.max_total_uncompressed or total_uncompressed > limits.max_total_uncompressed:
            _error("archive expanded size exceeds limit")
        if info.file_size:
            ratio = math.inf if not info.compress_size else info.file_size / info.compress_size
            if ratio > limits.max_compression_ratio:
                _error("archive compression ratio exceeds limit")

        # Keep source/ opaque. Prefix reads elsewhere are bounded and include
        # unreferenced entries, so disguised nested archives cannot bypass checks.
        if not info.is_dir() and not _is_source_path(name):
            if _looks_like_archive(_bounded_prefix_read(archive, info)):
                _error("nested archive entries are unsupported")

    manifests = [item for item in infos if item.filename == "manifest.json"]
    if len(manifests) != 1 or manifests[0].is_dir():
        _error("archive must contain exactly one root manifest.json")
    manifest_info = manifests[0]
    if manifest_info.file_size > limits.max_manifest_bytes:
        _error("manifest size exceeds limit")

    return infos, manifest_info, total_uncompressed


def _bounded_read(archive, info, limit, label):
    if info.file_size > limit:
        _error(label + " size exceeds limit")
    chunks = []
    total = 0
    try:
        with archive.open(info, "r") as member:
            while True:
                chunk = member.read(min(64 * 1024, limit + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    _error(label + " actual size exceeds limit")
                chunks.append(chunk)
    except ArchiveError:
        raise
    except (OSError, RuntimeError, EOFError, zipfile.BadZipFile, NotImplementedError, zlib.error) as exc:
        _error("unable to read " + label, exc)
    if total != info.file_size:
        _error(label + " size does not match ZIP metadata")
    return b"".join(chunks)


def _open_regular_archive(path):
    """Check an input path before opening, then verify its opened descriptor."""
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            _error("archive input must be a regular file")
    except OSError as exc:
        _error("unable to open MotionPack archive", exc)

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nonblocking = getattr(os, "O_NONBLOCK", None)
    if nonblocking is not None:
        flags |= nonblocking

    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        _error("unable to open MotionPack archive", exc)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            _error("archive input must be a regular file")
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _canonical_asset_path(raw_path):
    if not isinstance(raw_path, str) or not raw_path or "\x00" in raw_path or "\\" in raw_path:
        _error("unsafe manifest asset path")
    if raw_path.startswith("/") or re.match(r"^[A-Za-z]:", raw_path):
        _error("unsafe manifest asset path")
    parts = raw_path.split("/")
    if any(part == ".." for part in parts):
        _error("unsafe manifest asset path")
    canonical = pathlib.PurePosixPath(raw_path).as_posix()
    _member_parts(canonical)
    return canonical


def read_package(path, *, limits=None):
    """Read and validate a .motionpack without extracting arbitrary ZIP members.

    Referenced assets are read under per-file and aggregate limits. Unreferenced
    entries, including optional ``source/`` files, are metadata-checked and
    counted against archive limits but are not decompressed or returned.
    """
    limits = limits or ReaderLimits()
    if not isinstance(limits, ReaderLimits):
        raise TypeError("limits must be a ReaderLimits instance")
    source = pathlib.Path(path)
    try:
        with _open_regular_archive(source) as source_file:
            source_file.seek(0, 2)
            archive_size = source_file.tell()
            if archive_size > limits.max_archive_bytes:
                _error("archive file size exceeds limit")
            _preflight_end_record(source_file, archive_size, limits)
            source_file.seek(0)
            with zipfile.ZipFile(source_file, "r") as archive:
                infos, manifest_info, _ = _preflight(archive, limits)
                manifest_raw = _bounded_read(archive, manifest_info, limits.max_manifest_bytes, "manifest")
                try:
                    manifest_text = manifest_raw.decode("utf-8")
                    check_json_nesting(manifest_text)
                    manifest = json.loads(
                        manifest_text,
                        object_pairs_hook=_json_object,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON number")),
                    )
                except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
                    _error("invalid package manifest", exc)
                if not isinstance(manifest, dict):
                    _error("manifest must be a JSON object")

                entries = {info.filename: info for info in infos if not info.is_dir()}
                canonical_entries = {
                    unicodedata.normalize("NFC", name): info for name, info in entries.items()
                }
                declared_assets = manifest.get("assets")
                if not isinstance(declared_assets, dict) or len(declared_assets) > MAX_ASSETS:
                    _error("invalid or excessive manifest assets")

                resolved = {}
                for asset_id, raw_path in declared_assets.items():
                    if not isinstance(asset_id, str):
                        _error("invalid manifest asset ID")
                    asset_path = _canonical_asset_path(raw_path)
                    if _is_source_path(asset_path):
                        _error("source entries cannot be referenced as runtime assets")
                    key = unicodedata.normalize("NFC", asset_path)
                    info = canonical_entries.get(key)
                    if info is None or info.filename == "manifest.json":
                        _error("manifest references a missing archive asset")
                    resolved[asset_id] = info

                unique_infos = {info.filename: info for info in resolved.values()}
                if len(unique_infos) > MAX_ASSETS:
                    _error("too many referenced assets")
                declared_total = sum(info.file_size for info in unique_infos.values())
                if declared_total > limits.max_total_assets_bytes:
                    _error("declared total asset size exceeds limit")
                assets = {}
                loaded_by_entry = {}
                for asset_id, info in resolved.items():
                    if info.filename not in loaded_by_entry:
                        data = _bounded_read(archive, info, limits.max_asset_bytes, "asset")
                        if data.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
                            _error("nested archive asset is unsupported")
                        loaded_by_entry[info.filename] = data
                    assets[asset_id] = loaded_by_entry[info.filename]

        # Reuse the v0.1/v0.2/v0.3 semantic validator on a private temporary
        # tree containing only the manifest and referenced assets. Canonical entry
        # paths ensure aliases of one ZIP entry count once for PNG pixel budgets.
        # No ZIP member controls the temporary path and no caller-selected destination is used.
        with tempfile.TemporaryDirectory(prefix="motionpack-reader-") as temp_name:
            root = pathlib.Path(temp_name)
            validation_manifest = dict(manifest)
            validation_assets = dict(declared_assets)
            for asset_id, info in resolved.items():
                validation_assets[asset_id] = info.filename
            validation_manifest["assets"] = validation_assets
            validation_payload = json.dumps(validation_manifest).encode("utf-8")
            (root / "manifest.json").write_bytes(validation_payload)
            by_path = {}
            for asset_id, info in resolved.items():
                by_path.setdefault(info.filename, assets[asset_id])
            for relative_path, data in by_path.items():
                destination = root.joinpath(*pathlib.PurePosixPath(relative_path).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            try:
                errors, _ = validate(
                    root,
                    max_png_dimension=limits.max_png_dimension,
                    max_png_pixels=limits.max_png_pixels,
                    max_total_png_pixels=limits.max_total_png_pixels,
                    max_raster_dimension=limits.max_raster_dimension,
                    max_raster_pixels=limits.max_raster_pixels,
                    max_total_raster_pixels=limits.max_total_raster_pixels,
                    max_svg_dimension=limits.max_svg_dimension,
                    max_svg_pixels=limits.max_svg_pixels,
                )
            except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError, OverflowError) as exc:
                _error("invalid package manifest or assets", exc)
            if errors:
                _error("invalid package manifest or assets: " + "; ".join(errors))
        return MotionPackArchive(manifest=manifest, assets=assets)
    except ArchiveError:
        raise
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, EOFError, UnicodeDecodeError, OverflowError, zlib.error, struct.error) as exc:
        _error("unable to read MotionPack archive", exc)
