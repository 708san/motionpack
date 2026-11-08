#!/usr/bin/env python3
"""Regenerate the frozen v0.3/v0.4 compatibility packages deterministically."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from package import canonicalize_manifest
from validate import validate

EXAMPLES = (("layered_plant_demo", "0.3"), ("interaction_demo", "0.4"))
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "compatibility_archive_reader"
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def build_fixture(example: str, version: str, output_dir: Path) -> tuple[Path, str]:
    project = ROOT / "examples" / example
    asset_bytes: dict[str, bytes] = {}
    errors, manifest = validate(project, asset_data_sink=asset_bytes)
    if errors:
        raise ValueError(f"{example} failed validation: {'; '.join(errors)}")
    if manifest.get("version") != version:
        raise ValueError(f"{example} must declare v{version}")

    manifest = canonicalize_manifest(manifest)
    payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    entries: list[tuple[str, bytes]] = [("manifest.json", payload)]
    for asset_path in dict.fromkeys(manifest["assets"].values()):
        entries.append((asset_path, asset_bytes[asset_path]))

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"valid_v{version.replace('.', '')}.motionpack"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return archive_path, digest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=FIXTURE_DIR)
    args = parser.parse_args()
    for example, version in EXAMPLES:
        path, digest = build_fixture(example, version, args.output_dir)
        print(f"{digest}  {path.name}")


if __name__ == "__main__":
    main()
