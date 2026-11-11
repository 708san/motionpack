import base64
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tools import dependency_inventory as inventory

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
IMAGE_DIGEST = "sha256:" + "b" * 64


def write_npm_fixture(root, resolved="https://registry.npmjs.org/pkg/-/pkg-1.0.0.tgz",
                      integrity="sha512-" + base64.b64encode(bytes(64)).decode()):
    (root / "package.json").write_text("{}", encoding="utf-8")
    (root / "package-lock.json").write_text(json.dumps({
        "lockfileVersion": 3,
        "packages": {
            "": {},
            "node_modules/pkg": {
                "name": "pkg", "version": "1.0.0", "resolved": resolved,
                "integrity": integrity, "license": "MIT"
            }
        }
    }), encoding="utf-8")


class DependencyInventoryTests(unittest.TestCase):
    def test_checked_inventory_is_deterministic_and_current(self):
        generated = inventory.render_inventory(ROOT)
        checked = (ROOT / "docs" / "DEPENDENCY_INVENTORY.json").read_text(encoding="utf-8")
        self.assertEqual(generated, checked)
        self.assertEqual(generated, inventory.render_inventory(ROOT))
        data = json.loads(generated)
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(
            {item["ecosystem"] for item in data["dependencies"]},
            {"pypi", "npm", "github-action", "oci-image"},
        )
        self.assertTrue(data["coverage"]["not_covered"])

    def test_check_mode_detects_drift_without_rewriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "inventory.json"
            output.write_text("stale\n", encoding="utf-8")
            self.assertEqual(inventory.main(["--root", str(ROOT), "--output", str(output), "--check"]), 1)
            self.assertEqual(output.read_text(encoding="utf-8"), "stale\n")
            output.write_text(inventory.render_inventory(ROOT), encoding="utf-8")
            self.assertEqual(inventory.main(["--root", str(ROOT), "--output", str(output), "--check"]), 0)

    def test_relative_output_rejects_symlinked_parent(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            for pattern in ("requirements-*.txt",):
                for source in ROOT.glob(pattern):
                    shutil.copy2(source, root / source.name)
            for name in ("package.json", "package-lock.json"):
                shutil.copy2(ROOT / name, root / name)
            workflows = root / ".github" / "workflows"
            workflows.mkdir(parents=True)
            for source in (ROOT / ".github" / "workflows").glob("*.yml"):
                shutil.copy2(source, workflows / source.name)
            (root / "docs").symlink_to(Path(outside), target_is_directory=True)
            result = inventory.main(["--root", str(root)])
            self.assertEqual(result, 2)
            self.assertFalse((Path(outside) / "DEPENDENCY_INVENTORY.json").exists())

    def test_python_locks_are_exactly_pinned_and_hashed(self):
        entries = inventory.parse_requirements(ROOT)
        self.assertEqual({(e["name"].lower(), e["version"]) for e in entries},
                         {("atheris", "3.1.0"), ("pillow", "13.0.0")})
        for entry in entries:
            self.assertTrue(entry["hashes"])
            self.assertTrue(all(value.startswith("sha256:") for value in entry["hashes"]))

    def test_malformed_python_versions_are_rejected(self):
        for version in ("1..", "1+", "1.0.0!"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / "requirements-test.txt").write_text(
                    f"pkg=={version} --hash=sha256:{'a' * 64}\n", encoding="utf-8"
                )
                with self.assertRaisesRegex(ValueError, "unsupported or unpinned"):
                    inventory.parse_requirements(root)

    def test_invalid_requirement_error_does_not_echo_input(self):
        sentinel = "SECRET_SENTINEL_NO_ECHO"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "requirements-test.txt").write_text(
                f"pkg @ https://example.invalid/{sentinel}\n", encoding="utf-8"
            )
            with self.assertRaises(ValueError) as caught:
                inventory.parse_requirements(root)
            self.assertNotIn(sentinel, str(caught.exception))

    def test_python_source_file_count_and_total_size_are_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(5):
                (root / f"requirements-{index}.txt").write_bytes(b"#" * 900_000)
            with self.assertRaisesRegex(ValueError, "total input exceeds"):
                inventory.parse_requirements(root)

    def test_workflow_actions_and_images_are_pinned(self):
        entries = inventory.parse_workflows(ROOT)
        actions = [e for e in entries if e["ecosystem"] == "github-action"]
        images = [e for e in entries if e["ecosystem"] == "oci-image"]
        self.assertEqual(len(actions), 3)
        self.assertTrue(all(len(e["commit"]) == 40 for e in actions))
        self.assertEqual(len(images), 1)
        self.assertRegex(images[0]["digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(images[0]["license"]["status"], "not-assessed-composite-image")

    def test_symlinked_workflow_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            external = Path(outside)
            (external / "ci.yml").write_text("jobs: {}\n", encoding="utf-8")
            (root / ".github").mkdir()
            (root / ".github" / "workflows").symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "may not be symlinks"):
                inventory.parse_workflows(root)

    def test_unpinned_action_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ".github" / "workflows"
            folder.mkdir(parents=True)
            (folder / "ci.yml").write_text("steps:\n  - uses: actions/checkout@v4\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "full commit SHA"):
                inventory.parse_workflows(Path(tmp))

    def test_quoted_workflow_dependency_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ".github" / "workflows"
            folder.mkdir(parents=True)
            (folder / "ci.yml").write_text(
                f"steps:\n  - \"uses\": actions/checkout@{SHA}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "dependency key syntax"):
                inventory.parse_workflows(Path(tmp))

    def test_explicit_yaml_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ".github" / "workflows"
            folder.mkdir(parents=True)
            (folder / "ci.yml").write_text(
                f"steps:\n  - ? uses\n    : actions/checkout@{SHA}\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "dependency key syntax"):
                inventory.parse_workflows(Path(tmp))

    def test_inline_workflow_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ".github" / "workflows"
            folder.mkdir(parents=True)
            (folder / "ci.yml").write_text(
                "jobs:\n  test:\n    services: { db: { image: example/db:latest } }\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "dependency key syntax"):
                inventory.parse_workflows(Path(tmp))

    def test_unpinned_container_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / ".github" / "workflows"
            folder.mkdir(parents=True)
            (folder / "ci.yml").write_text(
                "jobs:\n  test:\n    container: example/image:latest\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "digest-pinned"):
                inventory.parse_workflows(Path(tmp))

    def test_npm_lock_shape_and_sri_are_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text("{}", encoding="utf-8")
            lock = root / "package-lock.json"
            lock.write_text('{"lockfileVersion":3}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "packages object"):
                inventory.parse_npm(root)
            lock.write_text(json.dumps({"lockfileVersion": 3, "packages": {"": {}, "node_modules/pkg": []}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "package records"):
                inventory.parse_npm(root)
            write_npm_fixture(root, integrity=" ")
            with self.assertRaisesRegex(ValueError, "empty SRI"):
                inventory.parse_npm(root)
            write_npm_fixture(root, integrity="sha1-" + base64.b64encode(bytes(20)).decode())
            with self.assertRaisesRegex(ValueError, "invalid SRI"):
                inventory.parse_npm(root)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text("{}", encoding="utf-8")
            (root / "package-lock.json").write_text(
                '{"lockfileVersion":2,"lockfileVersion":3,"packages":{"":{}}}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid or too deeply nested"):
                inventory.parse_npm(root)

    def test_npm_direct_dependencies_match_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(json.dumps({"devDependencies": {"pkg": "1.0.0"}}), encoding="utf-8")
            (root / "package-lock.json").write_text(json.dumps({
                "lockfileVersion": 3, "packages": {"": {"devDependencies": {}}}
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "devDependencies differ"):
                inventory.parse_npm(root)

    def test_npm_manifest_dependencies_require_lockfile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                json.dumps({"dependencies": {"pkg": "1.0.0"}}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "package-lock.json is required"):
                inventory.parse_npm(root)

    def test_repeated_image_reference_preserves_workflow_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / ".github" / "workflows"
            folder.mkdir(parents=True)
            image = f"example/image:1.2@{IMAGE_DIGEST}"
            (folder / "a.yml").write_text(f"jobs:\n  test:\n    container: {image}\n", encoding="utf-8")
            (folder / "b.yml").write_text(f"jobs:\n  test:\n    container: {image}\n", encoding="utf-8")
            entries = inventory.parse_workflows(root)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["workflows"], ["a.yml", "b.yml"])

    def test_npm_urls_reject_credentials_ports_and_arbitrary_paths(self):
        sentinel = "SECRET_SENTINEL_NO_ECHO"
        bad_urls = [
            "https://token@registry.npmjs.org/pkg/-/pkg-1.0.0.tgz",
            "https://registry.npmjs.org:444/pkg/-/pkg-1.0.0.tgz",
            f"https://registry.npmjs.org/{sentinel}/pkg.tgz",
        ]
        for url in bad_urls:
            with self.subTest(url=url), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                write_npm_fixture(root, resolved=url)
                with self.assertRaises(ValueError) as caught:
                    inventory.parse_npm(root)
                self.assertNotIn(sentinel, str(caught.exception))

    def test_npm_registry_port_443_and_scoped_tarball_are_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text("{}", encoding="utf-8")
            url = "https://registry.npmjs.org:443/@scope/pkg/-/pkg-1.0.0.tgz"
            integrity = "sha512-" + base64.b64encode(bytes(64)).decode()
            (root / "package-lock.json").write_text(json.dumps({
                "lockfileVersion": 3,
                "packages": {"": {}, "node_modules/@scope/pkg": {
                    "name": "@scope/pkg", "version": "1.0.0",
                    "resolved": url, "integrity": integrity,
                }}
            }), encoding="utf-8")
            self.assertEqual(inventory.parse_npm(root)[0]["source"],
                             "https://registry.npmjs.org/@scope/pkg/-/pkg-1.0.0.tgz")


if __name__ == "__main__":
    unittest.main()
