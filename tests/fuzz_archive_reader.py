#!/usr/bin/env python3
"""Coverage-guided fuzz target for the untrusted ZIP reader."""
from pathlib import Path
import os
import stat
import sys
import tempfile

import atheris

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

with atheris.instrument_imports():
    from archive_reader import ArchiveError, read_package


MAX_INPUT_BYTES = 64 * 1024
MAX_CORPUS_FILES = 16
MAX_CORPUS_BYTES = 1024 * 1024
SEED_FILES = (
    "valid_v01.motionpack",
    "valid_v02.motionpack",
    "not_zip.seed",
    "truncated_eocd.seed",
    "invalid_manifest.seed",
    "duplicate_asset.seed",
)


def copy_seed_corpus(source, destination):
    source = Path(source)
    destination = Path(destination)
    entries = list(source.iterdir())
    if len(entries) > MAX_CORPUS_FILES or {entry.name for entry in entries} != set(SEED_FILES):
        raise ValueError("fuzz corpus files do not match the reviewed seed set")

    total_bytes = 0
    for name in SEED_FILES:
        seed = source / name
        flags = (
            os.O_RDONLY
            | getattr(os, "O_BINARY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        descriptor = os.open(seed, flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("fuzz corpus seed must be a regular file")
            remaining = MAX_INPUT_BYTES
            with os.fdopen(descriptor, "rb", closefd=False) as source_file:
                with (destination / name).open("wb") as destination_file:
                    while True:
                        chunk = source_file.read(min(8192, remaining + 1))
                        if not chunk:
                            break
                        if len(chunk) > remaining:
                            raise ValueError("fuzz corpus seed exceeds the maximum input size")
                        destination_file.write(chunk)
                        remaining -= len(chunk)
            size = MAX_INPUT_BYTES - remaining
            total_bytes += size
            if total_bytes > MAX_CORPUS_BYTES:
                raise ValueError("fuzz corpus exceeds the aggregate size limit")
        finally:
            os.close(descriptor)


def assert_package_consistent(package):
    if not isinstance(package.manifest, dict):
        raise AssertionError("reader returned a non-dict manifest")
    if not isinstance(package.manifest.get("assets"), dict):
        raise AssertionError("reader returned a manifest without an assets object")
    if set(package.assets) != set(package.manifest["assets"]):
        raise AssertionError("reader returned inconsistent manifest and asset IDs")
    if not all(isinstance(asset, bytes) for asset in package.assets.values()):
        raise AssertionError("reader returned a non-byte asset")


def make_test_one_input(input_path):
    @atheris.instrument_func
    def test_one_input(data):
        if len(data) > MAX_INPUT_BYTES:
            return
        input_path.write_bytes(data)
        try:
            package = read_package(input_path)
        except ArchiveError:
            return
        assert_package_consistent(package)

    return test_one_input


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: fuzz_archive_reader.py CORPUS_DIR [libFuzzer options]")
    source_corpus = Path(sys.argv[1])

    with tempfile.TemporaryDirectory(prefix="motionpack-fuzz-") as temp_dir:
        temp_root = Path(temp_dir)
        corpus = temp_root / "corpus"
        corpus.mkdir()
        copy_seed_corpus(source_corpus, corpus)
        for seed_name in ("valid_v01.motionpack", "valid_v02.motionpack"):
            assert_package_consistent(read_package(corpus / seed_name))

        sys.argv[1] = str(corpus)
        test_one_input = make_test_one_input(temp_root / "input.motionpack")
        atheris.Setup(sys.argv, test_one_input)
        atheris.Fuzz()


if __name__ == "__main__":
    main()
