import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from v1_capability_preflight import (
    APPROVED_CAPABILITY_IDS,
    MAX_JSON_NESTING,
    CapabilityPreflightError,
    UnsafeOptionalCapability,
    UnsupportedRequiredCapability,
    preflight_v1_capabilities,
)


def manifest_bytes(capabilities, **extra):
    value = {"format": "motionpack", "version": "1.0", "capabilities": capabilities}
    value.update(extra)
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


class V1CapabilityPreflightTests(unittest.TestCase):
    def test_accepts_approved_required_and_optional_ids_without_mutation(self):
        raw = manifest_bytes({
            "required": ["org.motionpack.ik.two-bone"],
            "optional": ["org.motionpack.interaction"],
        }, extensions={
            "example.invalid.data": {"opaque": [1, 2]},
            "example.invalid.text": 'brackets [ { ] } and an escaped quote: "',
        })
        before = bytes(raw)
        result = preflight_v1_capabilities(
            raw, supported_capabilities=APPROVED_CAPABILITY_IDS
        )
        self.assertEqual(result.required, ("org.motionpack.ik.two-bone",))
        self.assertEqual(result.optional, ("org.motionpack.interaction",))
        self.assertEqual(result.ignored_optional, ())
        self.assertEqual(raw, before)

    def test_rejects_unknown_required_capability(self):
        raw = manifest_bytes({"required": ["org.example.future"], "optional": []})
        with self.assertRaisesRegex(UnsupportedRequiredCapability, "org.example.future"):
            preflight_v1_capabilities(
                raw, supported_capabilities=APPROVED_CAPABILITY_IDS
            )

    def test_unknown_optional_fails_closed_without_safe_rule(self):
        raw = manifest_bytes({"required": [], "optional": ["org.example.future"]})
        with self.assertRaisesRegex(UnsafeOptionalCapability, "not declared safe to ignore"):
            preflight_v1_capabilities(
                raw, supported_capabilities=APPROVED_CAPABILITY_IDS
            )

    def test_unknown_optional_is_ignored_only_with_explicit_safe_rule(self):
        raw = manifest_bytes({"required": [], "optional": ["org.example.future"]})
        result = preflight_v1_capabilities(
            raw,
            supported_capabilities=APPROVED_CAPABILITY_IDS,
            safe_to_ignore_optional=frozenset({"org.example.future"}),
        )
        self.assertEqual(result.ignored_optional, ("org.example.future",))

    def test_accepts_manifest_at_exact_byte_limit(self):
        raw = manifest_bytes({"required": [], "optional": []})
        raw += b" " * (1_000_000 - len(raw))
        result = preflight_v1_capabilities(
            raw, supported_capabilities=APPROVED_CAPABILITY_IDS
        )
        self.assertEqual(result.required, ())

    def test_accepts_identifier_at_limit_and_rejects_one_over(self):
        identifier = "x" * 128
        accepted = manifest_bytes({"required": [], "optional": [identifier]})
        result = preflight_v1_capabilities(
            accepted,
            supported_capabilities=APPROVED_CAPABILITY_IDS,
            safe_to_ignore_optional=frozenset({identifier}),
        )
        self.assertEqual(result.ignored_optional, (identifier,))

        too_long = manifest_bytes({"required": [identifier + "x"], "optional": []})
        with self.assertRaisesRegex(CapabilityPreflightError, "printable ASCII identifier"):
            preflight_v1_capabilities(
                too_long, supported_capabilities=APPROVED_CAPABILITY_IDS
            )

    def test_rejects_invalid_utf8_and_deeply_nested_json(self):
        deeply_nested = (
            b'{"format":"motionpack","version":"1.0",'
            b'"capabilities":{"required":[],"optional":[]},"nested":'
            + b"[" * 10_000 + b"0" + b"]" * 10_000 + b"}"
        )
        for raw in (b"\xff", deeply_nested):
            with self.subTest(raw_prefix=raw[:8]):
                with self.assertRaisesRegex(CapabilityPreflightError, "invalid or too deeply nested"):
                    preflight_v1_capabilities(
                        raw, supported_capabilities=APPROVED_CAPABILITY_IDS
                    )

    def test_rejects_json_nesting_above_operational_limit(self):
        depth = MAX_JSON_NESTING + 1
        raw = (
            b'{"format":"motionpack","version":"1.0",'
            b'"capabilities":{"required":[],"optional":[]},"nested":'
            + b"[" * depth + b"0" + b"]" * depth + b"}"
        )
        with self.assertRaisesRegex(CapabilityPreflightError, "invalid or too deeply nested"):
            preflight_v1_capabilities(
                raw, supported_capabilities=APPROVED_CAPABILITY_IDS
            )

    def test_rejects_missing_or_non_object_capabilities(self):
        cases = [None, "bad", []]
        missing = json.dumps({"format": "motionpack", "version": "1.0"}).encode()
        with self.assertRaisesRegex(CapabilityPreflightError, "requires a capabilities object"):
            preflight_v1_capabilities(missing, supported_capabilities=APPROVED_CAPABILITY_IDS)
        for value in cases:
            with self.subTest(value=value):
                raw = manifest_bytes(value)
                with self.assertRaisesRegex(CapabilityPreflightError, "requires a capabilities object"):
                    preflight_v1_capabilities(raw, supported_capabilities=APPROVED_CAPABILITY_IDS)

    def test_requires_exact_required_optional_array_fields(self):
        for capabilities in ({"required": []}, {"optional": []},
                             {"required": [], "optional": [], "extra": []}):
            with self.subTest(capabilities=capabilities):
                with self.assertRaisesRegex(CapabilityPreflightError, "exactly required and optional"):
                    preflight_v1_capabilities(
                        manifest_bytes(capabilities),
                        supported_capabilities=APPROVED_CAPABILITY_IDS,
                    )

    def test_both_fields_must_be_json_arrays(self):
        for capabilities in (
            {"required": "org.motionpack.ik.two-bone", "optional": []},
            {"required": [], "optional": None},
        ):
            with self.subTest(capabilities=capabilities):
                with self.assertRaises(CapabilityPreflightError):
                    preflight_v1_capabilities(
                        manifest_bytes(capabilities),
                        supported_capabilities=APPROVED_CAPABILITY_IDS,
                    )

    def test_rejects_non_string_empty_control_and_oversized_identifiers(self):
        values = [42, "", "org.example. bad", "org.example.\nkey", "x" * 129]
        for value in values:
            with self.subTest(value=repr(value)):
                raw = manifest_bytes({"required": [value], "optional": []})
                with self.assertRaisesRegex(CapabilityPreflightError, "printable ASCII identifier"):
                    preflight_v1_capabilities(
                        raw, supported_capabilities=APPROVED_CAPABILITY_IDS
                    )

    def test_rejects_duplicates_within_and_across_arrays(self):
        cases = [
            {"required": ["org.motionpack.ik.two-bone"] * 2, "optional": []},
            {"required": [], "optional": ["org.motionpack.interaction"] * 2},
            {"required": ["org.motionpack.interaction"], "optional": ["org.motionpack.interaction"]},
        ]
        for capabilities in cases:
            with self.subTest(capabilities=capabilities):
                with self.assertRaisesRegex(CapabilityPreflightError, "duplicate|both required and optional"):
                    preflight_v1_capabilities(
                        manifest_bytes(capabilities),
                        supported_capabilities=APPROVED_CAPABILITY_IDS,
                    )

    def test_rejects_unsupported_format_version(self):
        raw = json.dumps({
            "format": "motionpack", "version": "0.4",
            "capabilities": {"required": [], "optional": []},
        }).encode()
        with self.assertRaisesRegex(CapabilityPreflightError, "only a MotionPack v1.0"):
            preflight_v1_capabilities(raw, supported_capabilities=APPROVED_CAPABILITY_IDS)

    def test_rejects_oversized_manifest(self):
        raw = b" " * 1_000_001
        with self.assertRaisesRegex(CapabilityPreflightError, "byte limit"):
            preflight_v1_capabilities(raw, supported_capabilities=APPROVED_CAPABILITY_IDS)

    def test_rejects_duplicate_json_keys(self):
        raw = (b'{"format":"motionpack","version":"1.0",'
               b'"capabilities":{"required":[],"required":[],"optional":[]}}')
        with self.assertRaisesRegex(CapabilityPreflightError, "invalid or too deeply nested"):
            preflight_v1_capabilities(raw, supported_capabilities=APPROVED_CAPABILITY_IDS)

    def test_rejects_non_standard_json_constants(self):
        for constant in (b"NaN", b"Infinity", b"-Infinity"):
            raw = (
                b'{"format":"motionpack","version":"1.0",'
                b'"capabilities":{"required":[],"optional":[]},'
                b'"extensions":{"example.invalid.value":' + constant + b"}}"
            )
            with self.subTest(constant=constant):
                with self.assertRaisesRegex(CapabilityPreflightError, "invalid or too deeply nested"):
                    preflight_v1_capabilities(
                        raw, supported_capabilities=APPROVED_CAPABILITY_IDS
                    )

    def test_rejects_non_bytes_manifest_input(self):
        with self.assertRaisesRegex(CapabilityPreflightError, "manifest must be bytes"):
            preflight_v1_capabilities("{}", supported_capabilities=APPROVED_CAPABILITY_IDS)

    def test_accepts_bytearray_manifest_input(self):
        raw = bytearray(manifest_bytes({"required": [], "optional": []}))
        result = preflight_v1_capabilities(
            raw, supported_capabilities=APPROVED_CAPABILITY_IDS
        )
        self.assertEqual(result.optional, ())


if __name__ == "__main__":
    unittest.main()
