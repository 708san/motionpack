"""Read-only compatibility snapshots and normalized views for legacy packages.

The importer preserves source manifest and accepted ZIP payload bytes. It does
not convert, render, execute, or write a package.
"""
from dataclasses import dataclass, field
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
_IK_CAPABILITY = "org.motionpack.ik.two-bone"
_INTERACTION_CAPABILITY = "org.motionpack.interaction"
_SVG_DIMENSIONS_PROFILE = "org.motionpack.validation.svg-dimensions-v0.3"


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
class NormalizedRecord:
    """Immutable field-preserving view of a source manifest object."""

    values: Mapping
    present_fields: frozenset
    source_pointer: str


@dataclass(frozen=True)
class NormalizedNode:
    """Node projection retaining sparse authored fields and source location."""

    node_id: str
    asset_id: Optional[str]
    asset: Optional[ImportedAsset]
    asset_field_present: bool
    parent_id: Optional[str]
    parent_field_present: bool
    fields: Mapping
    present_fields: frozenset
    source_pointer: str


@dataclass(frozen=True)
class NormalizedClip:
    """Clip view with structural collections projected and sparse fields kept."""

    name: str
    duration_ms: int
    loop_present: bool
    loop_value: Optional[bool]
    tracks: tuple
    ik_tracks: tuple
    effects: tuple
    fields: Mapping
    present_fields: frozenset
    source_pointer: str


@dataclass(frozen=True)
class NormalizedVariant:
    """Sparse variant overlay view."""

    name: str
    node_overrides: Mapping
    fields: Mapping
    present_fields: frozenset
    source_pointer: str


@dataclass(frozen=True)
class CapabilityFact:
    """Observed content or version rule, with its evidence location."""

    identifier: str
    origin: str
    source_pointers: tuple
    interpretation: str
    diagnostic: Optional[str] = None


@dataclass(frozen=True)
class EffectiveValue:
    """A derived value kept separate from authored sparse data."""

    value: object
    source_version: str
    source_pointer: str
    field_present: bool
    rule_id: str
    rule_origin: str


@dataclass(frozen=True)
class NormalizedLegacyPackage:
    """Immutable engine-independent read model over a preserved legacy snapshot.

    This is an internal tooling view, not a v1 manifest or renderer-ready object.
    Sparse fields remain sparse; no defaults are materialized.
    """

    source_version: str
    identifier: Optional[str]
    manifest: Mapping
    manifest_bytes: bytes
    entries: Mapping
    assets: Mapping
    canvas: Mapping
    canvas_present: bool
    canvas_source_pointer: Optional[str]
    nodes: tuple
    clips: Mapping
    variants: Mapping
    defaults: Mapping
    defaults_present: bool
    defaults_source_pointer: Optional[str]
    ik_chains: tuple
    capability_facts: tuple
    validation_profiles: tuple
    diagnostics: tuple
    effective_defaults: Mapping = field(
        default_factory=lambda: MappingProxyType({})
    )

    @property
    def source_entries(self):
        """Opaque source-tree payloads, separate from runtime assets."""
        return MappingProxyType({
            name: payload for name, payload in self.entries.items()
            if name.split("/", 1)[0].casefold() == "source" and "/" in name
        })


@dataclass(frozen=True)
class LegacyImportSnapshot:
    """Validated, read-only view of a v0.1-v0.4 MotionPack archive."""

    source_version: str
    manifest: Mapping
    manifest_bytes: bytes
    assets: Mapping
    entries: Mapping
    capabilities: tuple
    validation_profiles: tuple
    report: ImportReport
    normalized: Optional[NormalizedLegacyPackage] = None

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


def _pointer(*segments):
    """Build an RFC 6901 JSON pointer from manifest path components."""
    escaped = (str(part).replace("~", "~0").replace("/", "~1") for part in segments)
    return "".join("/" + part for part in escaped)


def _record(value, pointer):
    return NormalizedRecord(
        values=_freeze(value),
        present_fields=frozenset(value),
        source_pointer=pointer,
    )


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
        capabilities.append(_IK_CAPABILITY)

    nodes = manifest.get("nodes")
    if isinstance(nodes, list) and any(
        isinstance(node, dict) and "interaction" in node for node in nodes
    ):
        capabilities.append(_INTERACTION_CAPABILITY)
    return tuple(capabilities)


def _capability_facts(manifest, version):
    facts = []
    ik_pointers = []
    if manifest.get("iks"):
        ik_pointers.append("/iks")
    for clip_name, clip in manifest.get("clips", {}).items():
        if isinstance(clip, dict) and clip.get("ik_tracks"):
            ik_pointers.append(_pointer("clips", clip_name, "ik_tracks"))
    if ik_pointers:
        mismatch = None
        interpretation = "observed"
        if version == "0.1":
            mismatch = (
                "IK content is interpreted according to current validator/runtime "
                "behavior although FORMAT_SPEC.md introduces IK in v0.2."
            )
            interpretation = "observed-with-version-spec-mismatch"
        facts.append(CapabilityFact(
            identifier=_IK_CAPABILITY,
            origin="observed-content",
            source_pointers=tuple(ik_pointers),
            interpretation=interpretation,
            diagnostic=mismatch,
        ))

    for index, node in enumerate(manifest.get("nodes", [])):
        if isinstance(node, dict) and "interaction" in node:
            facts.append(CapabilityFact(
                identifier=_INTERACTION_CAPABILITY,
                origin="observed-content",
                source_pointers=(_pointer("nodes", index, "interaction"),),
                interpretation="observed",
            ))

    if version in ("0.3", "0.4"):
        facts.append(CapabilityFact(
            identifier=_SVG_DIMENSIONS_PROFILE,
            origin="version-rule",
            source_pointers=("/version",),
            interpretation="applies-to-package",
        ))
    return tuple(facts)


def _normalize(manifest, frozen_manifest, manifest_bytes, assets, entries, version,
               validation_profiles, report_diagnostics):
    normalized_assets = MappingProxyType({
        asset_id: asset for asset_id, asset in assets.items()
    })

    nodes = []
    for index, raw_node in enumerate(manifest.get("nodes", [])):
        node_fields = {
            key: value for key, value in raw_node.items()
            if key not in ("id", "asset", "parent")
        }
        asset_present = "asset" in raw_node
        asset_id = raw_node.get("asset")
        parent_present = "parent" in raw_node
        nodes.append(NormalizedNode(
            node_id=raw_node["id"],
            asset_id=asset_id,
            asset=assets.get(asset_id) if asset_id is not None else None,
            asset_field_present=asset_present,
            parent_id=raw_node.get("parent"),
            parent_field_present=parent_present,
            fields=_freeze(node_fields),
            present_fields=frozenset(raw_node),
            source_pointer=_pointer("nodes", index),
        ))

    clips = {}
    for name, raw_clip in manifest.get("clips", {}).items():
        tracks = tuple(
            _record(item, _pointer("clips", name, "tracks", index))
            for index, item in enumerate(raw_clip.get("tracks", []))
        )
        ik_tracks = tuple(
            _record(item, _pointer("clips", name, "ik_tracks", index))
            for index, item in enumerate(raw_clip.get("ik_tracks", []))
        )
        effects = tuple(
            _record(item, _pointer("clips", name, "effects", index))
            for index, item in enumerate(raw_clip.get("effects", []))
        )
        loop_present = "loop" in raw_clip
        clip_fields = {
            key: value for key, value in raw_clip.items()
            if key not in ("duration_ms", "loop", "tracks", "ik_tracks", "effects")
        }
        clips[name] = NormalizedClip(
            name=name,
            duration_ms=raw_clip["duration_ms"],
            loop_present=loop_present,
            loop_value=raw_clip.get("loop"),
            tracks=tracks,
            ik_tracks=ik_tracks,
            effects=effects,
            fields=_freeze(clip_fields),
            present_fields=frozenset(raw_clip),
            source_pointer=_pointer("clips", name),
        )

    variants = {}
    for name, raw_variant in manifest.get("variants", {}).items():
        raw_overrides = raw_variant.get("nodes", {})
        overrides = MappingProxyType({
            node_id: _record(overlay, _pointer("variants", name, "nodes", node_id))
            for node_id, overlay in raw_overrides.items()
        })
        variant_fields = {
            key: value for key, value in raw_variant.items() if key != "nodes"
        }
        variants[name] = NormalizedVariant(
            name=name,
            node_overrides=overrides,
            fields=_freeze(variant_fields),
            present_fields=frozenset(raw_variant),
            source_pointer=_pointer("variants", name),
        )

    ik_chains = tuple(
        _record(item, _pointer("iks", index))
        for index, item in enumerate(manifest.get("iks", []))
    )
    effective_defaults = {}
    for clip_name, clip in manifest.get("clips", {}).items():
        if "loop" not in clip:
            pointer = _pointer("clips", clip_name, "loop")
            effective_defaults[pointer] = EffectiveValue(
                value=False,
                source_version=version,
                source_pointer=pointer,
                field_present=False,
                rule_id="motionpack.v0.clip.loop.default-false",
                rule_origin="format-spec",
            )

    if version in ("0.2", "0.3", "0.4"):
        for index, chain in enumerate(manifest.get("iks", [])):
            if "weight" not in chain:
                pointer = _pointer("iks", index, "weight")
                effective_defaults[pointer] = EffectiveValue(
                    value=1,
                    source_version=version,
                    source_pointer=pointer,
                    field_present=False,
                    rule_id="motionpack.v0.2.ik.weight.default-one",
                    rule_origin="format-spec",
                )

    capabilities = _capability_facts(manifest, version)
    diagnostics = list(report_diagnostics)
    diagnostics.extend(
        fact.diagnostic for fact in capabilities if fact.diagnostic is not None
    )
    canvas_present = "canvas" in manifest
    defaults_present = "defaults" in manifest
    return NormalizedLegacyPackage(
        source_version=version,
        identifier=manifest.get("id"),
        manifest=frozen_manifest,
        manifest_bytes=manifest_bytes,
        entries=entries,
        assets=normalized_assets,
        canvas=frozen_manifest.get("canvas", MappingProxyType({})),
        canvas_present=canvas_present,
        canvas_source_pointer="/canvas" if canvas_present else None,
        nodes=tuple(nodes),
        clips=MappingProxyType(clips),
        variants=MappingProxyType(variants),
        defaults=frozen_manifest.get("defaults", MappingProxyType({})),
        defaults_present=defaults_present,
        defaults_source_pointer="/defaults" if defaults_present else None,
        ik_chains=ik_chains,
        capability_facts=capabilities,
        validation_profiles=validation_profiles,
        diagnostics=tuple(diagnostics),
        effective_defaults=MappingProxyType(effective_defaults),
    )


def import_legacy_package(path, *, limits: Optional[ReaderLimits] = None,
                          timeout=30.0, memory_limit_bytes=None):
    """Import a validated v0.1-v0.4 package into an immutable normalized snapshot.

    All regular-file payloads are retained as opaque bytes. If the isolated
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
    frozen_assets = MappingProxyType(assets)
    frozen_entries = MappingProxyType(dict(package.entries or {}))
    frozen_manifest = _freeze(package.manifest)

    unknown_fields = tuple(sorted(set(package.manifest) - _KNOWN_TOP_LEVEL_FIELDS))
    capabilities = _derive_capabilities(package.manifest)
    validation_profiles = (
        (_SVG_DIMENSIONS_PROFILE,) if version in ("0.3", "0.4") else ()
    )
    base_diagnostics = (
        "Nested unknown manifest fields are preserved but not semantically classified.",
        "ZIP container metadata is not retained; only accepted regular-file payload bytes are preserved.",
    )
    report = ImportReport(
        unrecognized_manifest_fields=unknown_fields,
        preserved_file_count=len(frozen_entries),
        preserved_payload_bytes=sum(len(data) for data in frozen_entries.values()),
        container_metadata_not_retained=_NOT_RETAINED_CONTAINER_METADATA,
        diagnostics=base_diagnostics + tuple(
            fact.diagnostic for fact in _capability_facts(package.manifest, version)
            if fact.diagnostic is not None
        ),
    )
    normalized = _normalize(
        package.manifest, frozen_manifest, package.manifest_bytes, frozen_assets, frozen_entries,
        version, validation_profiles, base_diagnostics,
    )
    return LegacyImportSnapshot(
        source_version=version,
        manifest=frozen_manifest,
        manifest_bytes=package.manifest_bytes,
        assets=frozen_assets,
        entries=frozen_entries,
        capabilities=capabilities,
        validation_profiles=validation_profiles,
        report=report,
        normalized=normalized,
    )
