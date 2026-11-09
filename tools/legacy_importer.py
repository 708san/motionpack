"""Read-only in-memory compatibility snapshots for legacy MotionPack packages.

The importer preserves the source manifest and accepted ZIP payload bytes. It
does not convert, render, execute, or write a package.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

try:
    from .archive_reader import ReaderLimits
    from .isolated_archive_reader import read_package_isolated
except ImportError:  # Support direct import when tools/ is on sys.path.
    from archive_reader import ReaderLimits
    from isolated_archive_reader import read_package_isolated


_KNOWN_TOP_LEVEL_FIELDS = frozenset({
    "format", "version", "id", "canvas", "assets", "nodes", "clips",
    "variants", "defaults", "iks",
})
_NOT_RETAINED_CONTAINER_METADATA = (
    "compression method and compressed representation",
    "timestamps and permissions",
    "ZIP comments and extra fields",
    "directory-only entries",
    "ZIP member ordering and other container layout",
)


@dataclass(frozen=True)
class ImportedAsset:
    """One runtime asset resolved by its legacy manifest ID."""

    asset_id: str
    path: str
    data: bytes


@dataclass(frozen=True)
class ImportReport:
    """Preservation and interpretation diagnostics for one snapshot."""

    unrecognized_manifest_fields: tuple
    preserved_file_count: int
    preserved_payload_bytes: int
    container_metadata_not_retained: tuple
    diagnostics: tuple


@dataclass(frozen=True)
class LegacyImportSnapshot:
    """Validated, read-only view of a v0.1-v0.4 MotionPack archive."""

    source_version: str
    manifest: dict
    manifest_bytes: bytes
    assets: dict
    entries: dict
    capabilities: tuple
    validation_profiles: tuple
    report: ImportReport

    @property
    def source_entries(self):
        """Opaque source-tree payloads, separate from runtime assets."""
        return MappingProxyType({
            name: payload for name, payload in self.entries.items()
            if name.split("/", 1)[0].casefold() == "source" and "/" in name
        })


def _freeze(value):
    """Recursively expose parsed JSON as immutable mappings and tuples."""
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _derive_capabilities(manifest):
    capabilities = []
    iks = manifest.get("iks")
    clips = manifest.get("clips")
    has_ik_tracks = (
        isinstance(clips, dict)
        and any(
            isinstance(clip, dict) and isinstance(clip.get("ik_tracks"), list)
            and len(clip["ik_tracks"]) > 0
            for clip in clips.values()
        )
    )
    if (isinstance(iks, list) and iks) or has_ik_tracks:
        capabilities.append("org.motionpack.ik.two-bone")

    nodes = manifest.get("nodes")
    if isinstance(nodes, list) and any(
        isinstance(node, dict) and "interaction" in node for node in nodes
    ):
        capabilities.append("org.motionpack.interaction")
    return tuple(capabilities)


def import_legacy_package(path, *, limits: Optional[ReaderLimits] = None,
                          timeout=30.0, memory_limit_bytes=None):
    """Import a validated v0.1-v0.4 package into a read-only memory snapshot.

    All regular file payloads are retained as opaque bytes. If the isolated
    reader cannot return the complete snapshot within its response ceiling,
    the operation raises and returns no partial snapshot.
    """
    package = read_package_isolated(
        path,
        limits=limits,
        timeout=timeout,
        memory_limit_bytes=memory_limit_bytes,
        include_entries=True,
    )
    version = package.manifest.get("version")
    if version not in ("0.1", "0.2", "0.3", "0.4"):
        # The underlying semantic validator normally rejects this first. Keep
        # the importer boundary explicit if a future reader accepts more.
        raise ValueError("unsupported legacy MotionPack version")

    assets = {}
    declarations = package.manifest.get("assets", {})
    for asset_id, asset_path in declarations.items():
        assets[asset_id] = ImportedAsset(
            asset_id=asset_id,
            path=asset_path,
            data=package.assets[asset_id],
        )

    unknown_fields = tuple(sorted(set(package.manifest) - _KNOWN_TOP_LEVEL_FIELDS))
    capabilities = _derive_capabilities(package.manifest)
    validation_profiles = (
        ("org.motionpack.validation.svg-dimensions-v0.3",)
        if version in ("0.3", "0.4") else ()
    )
    diagnostics = (
        "Nested unknown manifest fields are preserved but not semantically classified.",
        "ZIP container metadata is not retained; only accepted regular-file payload bytes are preserved.",
    )
    report = ImportReport(
        unrecognized_manifest_fields=unknown_fields,
        preserved_file_count=len(package.entries or {}),
        preserved_payload_bytes=sum(len(data) for data in (package.entries or {}).values()),
        container_metadata_not_retained=_NOT_RETAINED_CONTAINER_METADATA,
        diagnostics=diagnostics,
    )
    return LegacyImportSnapshot(
        source_version=version,
        manifest=_freeze(package.manifest),
        manifest_bytes=package.manifest_bytes,
        assets=MappingProxyType(assets),
        entries=MappingProxyType(dict(package.entries or {})),
        capabilities=capabilities,
        validation_profiles=validation_profiles,
        report=report,
    )
