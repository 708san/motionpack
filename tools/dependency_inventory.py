"""Build an offline dependency inventory from pinned repository declarations."""
import argparse
import base64
import binascii
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 4_000_000
MAX_SOURCE_FILES = 64
PYTHON_VERSION = r"[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+|\.post[0-9]+|\.dev[0-9]+)?(?:\+[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?"
REQUIREMENT = re.compile(rf"^([A-Za-z0-9][A-Za-z0-9_.-]*)==({PYTHON_VERSION})$")
REQUIREMENT_HASH = re.compile(r"^\s*--hash=sha256:([0-9a-f]{64})\s*\\?$")
ACTION_REF = re.compile(
    r"^\s*(?:-\s*)?uses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@([0-9a-f]{40})(?:\s*#\s*(.*))?$"
)
PYTHON_LICENSES = {
    ("atheris", "3.1.0"): {
        "status": "maintainer-documented",
        "expression": "Apache-2.0",
        "evidence": "SECURITY.md",
    },
    ("pillow", "13.0.0"): {
        "status": "upstream-license-file",
        "expression": "MIT-CMU",
        "evidence": "https://github.com/python-pillow/Pillow/blob/13.0.0/LICENSE",
    },
}
ACTION_LICENSES = {
    "actions/checkout": "MIT",
    "actions/setup-python": "MIT",
    "actions/upload-artifact": "MIT",
}
SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
)
SPDX_LIKE = re.compile(r"[A-Za-z0-9.+()-]+(?:\s+(?:AND|OR|WITH)\s+[A-Za-z0-9.+()-]+)*")
OCI_IMAGE = re.compile(
    r"([A-Za-z0-9.-]+(?::[0-9]{1,5})?)/"
    r"([a-z0-9]+(?:[._/-][a-z0-9]+)*):"
    r"(v?[0-9]+(?:\.[0-9]+){1,2}(?:[-+][A-Za-z0-9.-]+)?)"
)


def check_budget(paths):
    paths = list(paths)
    if len(paths) > MAX_SOURCE_FILES:
        raise ValueError(f"dependency inventory source file count exceeds {MAX_SOURCE_FILES}")
    total = 0
    for path in paths:
        if path.is_symlink():
            raise ValueError("dependency inventory inputs may not be symlinks")
        try:
            total += path.stat().st_size
        except OSError as exc:
            raise ValueError("unable to stat dependency inventory input") from exc
        if total > MAX_TOTAL_BYTES:
            raise ValueError("dependency inventory total input exceeds 4 MiB")


def read(path):
    if path.is_symlink():
        raise ValueError("dependency inventory inputs may not be symlinks")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError("unable to stat dependency inventory input") from exc
    if size > MAX_FILE_BYTES:
        raise ValueError(f"{path.name}: input exceeds {MAX_FILE_BYTES} bytes")
    return path.read_text(encoding="utf-8")


def reject_duplicate_json_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON input contains a duplicate object key")
        result[key] = value
    return result


def strict_json_loads(source):
    return json.loads(source, object_pairs_hook=reject_duplicate_json_keys)


def safe_npm_tarball_url(url, package_name, version):
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("package-lock.json has an invalid resolved URL") from exc
    if (
        any(ord(char) < 0x20 for char in url)
        or parsed.scheme != "https"
        or parsed.hostname != "registry.npmjs.org"
        or port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("package-lock.json resolved URL must be credential-free HTTPS on registry.npmjs.org")
    leaf = package_name.rsplit("/", 1)[-1]
    expected_path = f"/{package_name}/-/{leaf}-{version}.tgz"
    if unquote(parsed.path) != expected_path:
        raise ValueError("package-lock.json tarball path must match the locked package name and version")
    return "https://registry.npmjs.org" + expected_path


def parse_requirements(root):
    entries = {}
    files = sorted(root.glob("requirements-*.txt"))
    if not files:
        raise ValueError("no requirements-*.txt locks found")
    check_budget(files)
    for path in files:
        group = path.stem.removeprefix("requirements-")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", group):
            raise ValueError("requirements lock filename has unsupported group syntax")
        active = None
        for line_number, raw in enumerate(read(path).splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            candidate = line[:-1].rstrip() if line.endswith("\\") else line
            match = REQUIREMENT.fullmatch(candidate)
            if match:
                name, version = match.groups()
                normalized_name = re.sub(r"[-_.]+", "-", name).lower()
                key = normalized_name, version
                entry = entries.setdefault(key, {
                    "ecosystem": "pypi",
                    "name": name,
                    "version": version,
                    "source": f"https://pypi.org/project/{name.lower()}/{version}/",
                    "groups": [],
                    "hashes": [],
                })
                if group not in entry["groups"]:
                    entry["groups"].append(group)
                active = entry
                continue
            match = REQUIREMENT_HASH.fullmatch(raw)
            if match and active is not None:
                active["hashes"].append("sha256:" + match.group(1))
                continue
            raise ValueError(f"{path.name}:{line_number}: unsupported or unpinned requirement syntax")
    result = []
    for key, entry in sorted(entries.items()):
        if not entry["hashes"]:
            raise ValueError(f"{entry['name']}=={entry['version']} has no SHA-256 hash")
        entry["groups"].sort()
        entry["hashes"] = sorted(set(entry["hashes"]))
        entry["license"] = PYTHON_LICENSES.get(
            key, {"status": "unreviewed", "expression": None, "evidence": None}
        )
        result.append(entry)
    return result


def parse_npm(root):
    lock_path = root / "package-lock.json"
    if not lock_path.exists():
        manifest_path = root / "package.json"
        if manifest_path.exists():
            check_budget([manifest_path])
            try:
                manifest = strict_json_loads(read(manifest_path))
            except (json.JSONDecodeError, RecursionError, ValueError) as exc:
                raise ValueError("package.json is invalid or too deeply nested") from exc
            if not isinstance(manifest, dict):
                raise ValueError("package.json root must be an object")
            for group in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
                declared = manifest.get(group, {})
                if not isinstance(declared, dict):
                    raise ValueError(f"package.json {group} must be an object")
                if declared:
                    raise ValueError("package-lock.json is required when package.json declares dependencies")
        return []
    manifest_path = root / "package.json"
    if not manifest_path.exists():
        raise ValueError("package.json is required when package-lock.json exists")
    check_budget([lock_path, manifest_path])
    try:
        lock = strict_json_loads(read(lock_path))
        manifest = strict_json_loads(read(manifest_path))
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ValueError("package.json or package-lock.json is invalid or too deeply nested") from exc
    if not isinstance(lock, dict):
        raise ValueError("package-lock.json root must be an object")
    if lock.get("lockfileVersion") != 3:
        raise ValueError("package-lock.json must use lockfileVersion 3")
    packages = lock.get("packages")
    if not isinstance(packages, dict) or "" not in packages:
        raise ValueError("package-lock.json must contain a packages object and root package")
    root_package = packages[""]
    if not isinstance(root_package, dict):
        raise ValueError("package-lock.json root package must be an object")
    if not isinstance(manifest, dict):
        raise ValueError("package.json root must be an object")
    for group in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        declared = manifest.get(group, {})
        locked = root_package.get(group, {})
        if not isinstance(declared, dict) or not isinstance(locked, dict) or declared != locked:
            raise ValueError(f"package.json and package-lock.json root {group} differ")
    result = []
    for package_path, metadata in sorted(packages.items()):
        if not isinstance(package_path, str) or not isinstance(metadata, dict):
            raise ValueError("package-lock.json package records must be objects with string paths")
        if not package_path.startswith("node_modules/"):
            continue
        name = metadata.get("name")
        if not name:
            tail = package_path.split("node_modules/")[-1]
            name = "/".join(tail.split("/")[:2]) if tail.startswith("@") else tail.split("/", 1)[0]
        if not isinstance(name, str) or not re.fullmatch(
            r"(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9._-]+", name
        ):
            raise ValueError("package-lock.json contains an invalid package name")
        version = metadata.get("version")
        resolved = metadata.get("resolved")
        integrity = metadata.get("integrity")
        if (
            not isinstance(version, str)
            or not SEMVER.fullmatch(version)
            or not isinstance(resolved, str)
            or not isinstance(integrity, str)
        ):
            raise ValueError("package-lock.json package lacks a valid version, source, or integrity")
        resolved = safe_npm_tarball_url(resolved, name, version)
        digest_lengths = {"sha512": 64, "sha384": 48, "sha256": 32}
        integrity_tokens = integrity.split()
        if not integrity_tokens:
            raise ValueError("package-lock.json has empty SRI integrity")
        for token in integrity_tokens:
            match = re.fullmatch(r"(sha512|sha384|sha256)-([A-Za-z0-9+/]+={0,2})", token)
            if not match:
                raise ValueError("package-lock.json has invalid SRI integrity")
            algorithm, encoded = match.groups()
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise ValueError("package-lock.json has invalid SRI base64") from exc
            if len(decoded) != digest_lengths[algorithm]:
                raise ValueError("package-lock.json has invalid SRI digest length")
        license_value = metadata.get("license")
        if not isinstance(license_value, str) or not SPDX_LIKE.fullmatch(license_value):
            license_value = None
        result.append({
            "ecosystem": "npm",
            "name": name,
            "version": version,
            "source": resolved,
            "integrity": integrity,
            "license": {
                "status": "declared-in-lock" if license_value else "unreviewed",
                "expression": license_value,
                "evidence": "package-lock.json" if license_value else None,
            },
        })
    return result


def parse_workflows(root):
    github_directory = root / ".github"
    directory = github_directory / "workflows"
    if github_directory.is_symlink() or directory.is_symlink():
        raise ValueError("workflow directories may not be symlinks")
    files = sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
    if not files:
        raise ValueError("no GitHub workflow files found")
    check_budget(files)
    for path in files:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.ya?ml", path.name):
            raise ValueError("workflow filename contains unsupported characters")
    found = {}
    explicit_key = re.compile(
        r"^\s*(?:-\s*)?\?\s*['\"]?(?:uses|container|image)['\"]?\s*$"
    )
    key_hint = re.compile(
        r"""(?:["'](?:uses|container|image)["']\s*:|\b(?:uses|container|image)\s*:)"""
    )
    active_uses = re.compile(r"^\s*(?:-\s*)?uses\s*:")
    active_image = re.compile(r"^\s*(?:container|image)\s*:")
    for path in files:
        for line_number, line in enumerate(read(path).splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if explicit_key.match(line) or (
                key_hint.search(line) and not (active_uses.match(line) or active_image.match(line))
            ):
                raise ValueError(f"{path.name}:{line_number}: unsupported workflow dependency key syntax")
            if active_uses.match(line):
                match = ACTION_REF.fullmatch(line)
                if not match:
                    raise ValueError(f"{path.name}:{line_number}: action must use a full commit SHA")
                repository, commit, comment = match.groups()
                version_comment = None
                if comment and re.fullmatch(
                    r"v?[0-9]+(?:\.[0-9]+){1,2}(?:[-+][A-Za-z0-9.-]+)?", comment.strip()
                ):
                    version_comment = comment.strip()
                entry = found.setdefault((repository, commit), {
                    "ecosystem": "github-action",
                    "name": repository,
                    "version": version_comment,
                    "source": f"https://github.com/{repository}",
                    "commit": commit,
                    "workflows": [],
                    "license": {
                        "status": "pinned-license-file" if repository in ACTION_LICENSES else "unreviewed",
                        "expression": ACTION_LICENSES.get(repository),
                        "evidence": f"https://github.com/{repository}/blob/{commit}/LICENSE",
                    },
                })
                if path.name not in entry["workflows"]:
                    entry["workflows"].append(path.name)
            if active_image.match(line):
                value = line.split(":", 1)[1].strip()
                if value.startswith(("'", '"')) or "@sha256:" not in value:
                    raise ValueError(f"{path.name}:{line_number}: image must be literal and digest-pinned")
                image, digest = value.rsplit("@", 1)
                match = OCI_IMAGE.fullmatch(image)
                if not match or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                    raise ValueError(f"{path.name}:{line_number}: invalid OCI image reference")
                registry, _, tag = match.groups()
                image_key = ("image", image, digest)
                existing = found.get(image_key)
                if existing is not None:
                    if path.name not in existing["workflows"]:
                        existing["workflows"].append(path.name)
                    continue
                found[image_key] = {
                    "ecosystem": "oci-image",
                    "name": image,
                    "version": tag,
                    "source": f"https://{registry}",
                    "digest": digest,
                    "workflows": [path.name],
                    "license": {
                        "status": "not-assessed-composite-image",
                        "expression": None,
                        "evidence": "Nested OS/browser packages are not enumerated; obtain and review an image SBOM before release.",
                    },
                }
    for entry in found.values():
        entry["workflows"].sort()
    return sorted(
        found.values(),
        key=lambda entry: (
            entry["ecosystem"], entry["name"], entry.get("version") or "", entry.get("commit") or ""
        ),
    )


def build_inventory(root):
    sources = list(root.glob("requirements-*.txt"))
    sources.extend(
        root / name for name in ("package.json", "package-lock.json")
        if (root / name).exists()
    )
    workflow_directory = root / ".github" / "workflows"
    sources.extend(workflow_directory.glob("*.yml"))
    sources.extend(workflow_directory.glob("*.yaml"))
    check_budget(sources)
    dependencies = parse_requirements(root) + parse_npm(root) + parse_workflows(root)
    dependencies.sort(key=lambda entry: (
        entry["ecosystem"], entry["name"], entry.get("version") or "", entry.get("source") or ""
    ))
    return {
        "schema_version": 1,
        "coverage": {
            "python": "requirements-*.txt; exact versions and SHA-256 hashes required",
            "npm": "package-lock.json v3 entries; resolved URL, integrity and declared license",
            "github_actions": "unquoted block-style workflow uses references; full commit SHA required; quoted, inline and explicit-key forms fail closed",
            "container_images": "workflow image/container references; SHA-256 digest required",
            "not_covered": [
                "packages bundled inside third-party GitHub Actions",
                "OS/browser packages inside OCI images",
                "GitHub-hosted runner contents",
                "native libraries bundled inside binary wheels",
            ],
            "assurance": "Offline provenance/drift inventory, not a complete SBOM or license/legal determination",
        },
        "dependencies": dependencies,
    }


def render_inventory(root):
    return json.dumps(build_inventory(root), ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("docs/DEPENDENCY_INVENTORY.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    if not args.output.is_absolute():
        try:
            output.resolve().relative_to(root)
        except ValueError:
            print("relative dependency inventory output must stay within --root", file=sys.stderr)
            return 2
        current = root
        for part in args.output.parts[:-1]:
            if part in ("", "."):
                continue
            if part == "..":
                current = current.parent
            else:
                current = current / part
            if current.is_symlink():
                print("relative dependency inventory output parents may not be symlinks", file=sys.stderr)
                return 2
    try:
        expected = render_inventory(root)
    except (OSError, ValueError) as exc:
        print(f"dependency inventory: {exc}", file=sys.stderr)
        return 2
    if output.is_symlink():
        print("dependency inventory output may not be a symlink", file=sys.stderr)
        return 2
    if args.check:
        try:
            current = output.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""
        if current != expected:
            print(
                f"{output} is stale; regenerate with python3 tools/dependency_inventory.py",
                file=sys.stderr,
            )
            return 1
        print(f"Dependency inventory matches {output}")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(expected, encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
