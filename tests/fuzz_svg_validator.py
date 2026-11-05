#!/usr/bin/env python3
"""Coverage-guided fuzz target for the bounded SVG subset validator."""
from pathlib import Path
import os
import stat
import sys
import tempfile
from xml.parsers import expat

import atheris

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

with atheris.instrument_imports():
    from validate import validate_svg


MAX_INPUT_BYTES = 64 * 1024
MAX_CORPUS_FILES = 8
MAX_CORPUS_BYTES = 1024 * 1024
SEED_FILES = (
    "valid_minimal.svg",
    "valid_gradient.svg",
    "invalid_doctype.svg",
    "invalid_external_reference.svg",
    "invalid_css_url.svg",
    "invalid_unknown_attribute.svg",
    "malformed_xml.svg",
)
VALID_SEEDS = {"valid_minimal.svg", "valid_gradient.svg"}
EXPECTED_VALUE_ERRORS = {
    "DOCTYPE is forbidden",
    "entity declarations are forbidden",
    "processing instructions are forbidden",
    "nesting exceeds maximum depth",
    "element count exceeds maximum",
    "attribute count exceeds maximum",
    "attribute value exceeds maximum size",
    "SVG document is empty",
}


def copy_seed_corpus(source, destination):
    source = Path(source)
    destination = Path(destination)
    entries = []
    for entry in source.iterdir():
        entries.append(entry)
        if len(entries) > MAX_CORPUS_FILES:
            raise ValueError("SVG fuzz corpus exceeds the reviewed file-count limit")
    if {entry.name for entry in entries} != set(SEED_FILES):
        raise ValueError("SVG fuzz corpus files do not match the reviewed seed set")

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
                raise ValueError("SVG fuzz corpus seed must be a regular file")
            remaining = MAX_INPUT_BYTES
            with os.fdopen(descriptor, "rb", closefd=False) as source_file:
                with (destination / name).open("wb") as destination_file:
                    while True:
                        chunk = source_file.read(min(8192, remaining + 1))
                        if not chunk:
                            break
                        if len(chunk) > remaining:
                            raise ValueError("SVG fuzz corpus seed exceeds the maximum input size")
                        destination_file.write(chunk)
                        remaining -= len(chunk)
            total_bytes += MAX_INPUT_BYTES - remaining
            if total_bytes > MAX_CORPUS_BYTES:
                raise ValueError("SVG fuzz corpus exceeds the aggregate size limit")
        finally:
            os.close(descriptor)


def validate_input(data):
    try:
        return validate_svg(data)
    except ValueError as error:
        if str(error) not in EXPECTED_VALUE_ERRORS:
            raise
        return None
    except expat.ExpatError:
        return None


def make_test_one_input():
    @atheris.instrument_func
    def test_one_input(data):
        if len(data) > MAX_INPUT_BYTES:
            return
        errors = validate_input(data)
        if errors is None:
            return
        if not isinstance(errors, list) or not all(isinstance(error, str) for error in errors):
            raise AssertionError("SVG validator returned an invalid result")

    return test_one_input


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: fuzz_svg_validator.py CORPUS_DIR [libFuzzer options]")
    source_corpus = Path(sys.argv[1])

    with tempfile.TemporaryDirectory(prefix="motionpack-svg-fuzz-") as temp_dir:
        temp_root = Path(temp_dir)
        corpus = temp_root / "corpus"
        corpus.mkdir()
        copy_seed_corpus(source_corpus, corpus)
        for seed_name in SEED_FILES:
            errors = validate_input((corpus / seed_name).read_bytes())
            if seed_name in VALID_SEEDS and (errors is None or errors):
                raise AssertionError("reviewed valid SVG seed was rejected")
            if seed_name not in VALID_SEEDS and errors == []:
                raise AssertionError("reviewed invalid SVG seed was accepted")

        sys.argv[1] = str(corpus)
        atheris.Setup(sys.argv, make_test_one_input())
        atheris.Fuzz()


if __name__ == "__main__":
    main()
