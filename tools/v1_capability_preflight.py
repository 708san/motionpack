"""Experimental manifest-only v1 capability preflight.

This primitive does not load assets, start playback, or establish v1 conformance.
Callers must run it on bounded manifest bytes before any package asset is read.
"""
from dataclasses import dataclass
import json
import math
from typing import FrozenSet, Tuple

MAX_MANIFEST_BYTES = 1_000_000
MAX_JSON_NESTING = 128
APPROVED_CAPABILITY_IDS = frozenset({
    "org.motionpack.ik.two-bone",
    "org.motionpack.interaction",
})


class CapabilityPreflightError(ValueError):
    """Malformed capability metadata or a capability that cannot be ignored safely."""


class UnsupportedRequiredCapability(CapabilityPreflightError):
    """The reader does not support a capability required by this package."""


class UnsafeOptionalCapability(CapabilityPreflightError):
    """An unsupported optional capability lacks an explicit safe-ignore rule."""


@dataclass(frozen=True)
class CapabilityPreflight:
    """Capability declarations accepted for a later, separate load/play step."""

    required: Tuple[str, ...]
    optional: Tuple[str, ...]
    ignored_optional: Tuple[str, ...]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("manifest contains a duplicate JSON object key")
        result[key] = value
    return result


def _reject_json_constant(value):
    raise ValueError(f"non-standard JSON constant: {value}")


def _parse_finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("JSON number is outside the finite float range")
    return parsed


def _check_json_nesting(raw_manifest):
    depth = 0
    in_string = False
    escaped = False
    for byte in raw_manifest:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
        elif byte == 0x22:
            in_string = True
        elif byte in (0x7B, 0x5B):  # { or [
            depth += 1
            if depth > MAX_JSON_NESTING:
                raise ValueError("manifest exceeds the JSON nesting limit")
        elif byte in (0x7D, 0x5D):  # } or ]
            depth -= 1


def _decode_manifest(raw_manifest):
    if not isinstance(raw_manifest, (bytes, bytearray)):
        raise CapabilityPreflightError("manifest must be bytes")
    if len(raw_manifest) > MAX_MANIFEST_BYTES:
        raise CapabilityPreflightError("manifest exceeds the preflight byte limit")
    try:
        _check_json_nesting(raw_manifest)
        text = bytes(raw_manifest).decode("utf-8")
        manifest = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
            parse_float=_parse_finite_float,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise CapabilityPreflightError("manifest is invalid or too deeply nested") from exc
    if not isinstance(manifest, dict):
        raise CapabilityPreflightError("manifest root must be an object")
    if manifest.get("format") != "motionpack" or manifest.get("version") != "1.0":
        raise CapabilityPreflightError("preflight accepts only a MotionPack v1.0 manifest")
    return manifest


def _read_id_list(value, field):
    if not isinstance(value, list):
        raise CapabilityPreflightError(f"capabilities.{field} must be an array")
    identifiers = []
    seen = set()
    for index, identifier in enumerate(value):
        if (
            not isinstance(identifier, str)
            or not identifier
            or len(identifier) > 128
            or not identifier.isascii()
            or any(ord(char) < 0x21 or ord(char) > 0x7E for char in identifier)
        ):
            raise CapabilityPreflightError(
                f"capabilities.{field}[{index}] must be a non-empty printable ASCII identifier"
            )
        if identifier in seen:
            raise CapabilityPreflightError(f"capabilities.{field} contains a duplicate identifier")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


def preflight_v1_capabilities(
    raw_manifest: bytes,
    *,
    supported_capabilities: FrozenSet[str],
    safe_to_ignore_optional: FrozenSet[str] = frozenset(),
) -> CapabilityPreflight:
    """Validate v1 capability metadata without opening assets or starting playback.

    ``safe_to_ignore_optional`` is an explicit per-reader policy. Unknown optional
    capabilities fail closed unless the caller has a reviewed rule proving that
    omission is safe. This function is not yet wired into the v0.1-v0.4 reader.
    """
    manifest = _decode_manifest(raw_manifest)
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        raise CapabilityPreflightError("v1 manifest requires a capabilities object")
    if set(capabilities) != {"required", "optional"}:
        raise CapabilityPreflightError("capabilities must contain exactly required and optional arrays")

    required = _read_id_list(capabilities["required"], "required")
    optional = _read_id_list(capabilities["optional"], "optional")
    if set(required).intersection(optional):
        raise CapabilityPreflightError("a capability cannot be both required and optional")

    supported = frozenset(supported_capabilities)
    safe_optional = frozenset(safe_to_ignore_optional)
    unsupported_required = tuple(identifier for identifier in required if identifier not in supported)
    if unsupported_required:
        identifier = unsupported_required[0]
        raise UnsupportedRequiredCapability(f"unsupported required capability: {identifier}")

    ignored_optional = tuple(
        identifier for identifier in optional
        if identifier not in supported and identifier in safe_optional
    )
    unsafe_optional = tuple(
        identifier for identifier in optional
        if identifier not in supported and identifier not in safe_optional
    )
    if unsafe_optional:
        identifier = unsafe_optional[0]
        raise UnsafeOptionalCapability(
            f"unsupported optional capability is not declared safe to ignore: {identifier}"
        )
    return CapabilityPreflight(required, optional, ignored_optional)
