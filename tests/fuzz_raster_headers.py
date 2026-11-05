#!/usr/bin/env python3
"""Coverage-guided fuzz target for PNG, JPEG and WebP header parsers."""
from pathlib import Path
import os
import stat
import sys
import tempfile

import atheris

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

with atheris.instrument_imports():
    from validate import (
        MAX_PNG_DIMENSION,
        MAX_PNG_PIXELS,
        MAX_TOTAL_PNG_PIXELS,
        PNG_SPEC_MAX_DIMENSION,
        RasterHeaderError,
        RasterLimitError,
        parse_jpeg_dimensions,
        parse_png_dimensions,
        parse_webp_raster,
    )


MAX_INPUT_BYTES = 64 * 1024
MAX_CORPUS_FILES = 16
MAX_CORPUS_BYTES = 1024 * 1024
SEED_FILES = (
    "png_valid.seed",
    "png_bad_crc.seed",
    "png_truncated.seed",
    "png_zero_dimension.seed",
    "jpeg_baseline.seed",
    "jpeg_progressive.seed",
    "jpeg_bad_segment.seed",
    "jpeg_without_frame.seed",
    "webp_vp8x.seed",
    "webp_vp8.seed",
    "webp_vp8l.seed",
    "webp_animated.seed",
    "webp_bad_bounds.seed",
    "webp_truncated_riff.seed",
    "webp_simple_vp8_over_limit.seed",
    "webp_vp8l_over_dimension_limit.seed",
)
VALID_SEEDS = {
    "png_valid.seed",
    "jpeg_baseline.seed",
    "jpeg_progressive.seed",
    "webp_vp8x.seed",
    "webp_vp8.seed",
    "webp_vp8l.seed",
    "webp_animated.seed",
}


def copy_seed_corpus(source, destination):
    source = Path(source)
    destination = Path(destination)
    entries = []
    for entry in source.iterdir():
        entries.append(entry)
        if len(entries) > MAX_CORPUS_FILES:
            raise ValueError("raster fuzz corpus exceeds the reviewed file-count limit")
    if {entry.name for entry in entries} != set(SEED_FILES):
        raise ValueError("raster fuzz corpus files do not match the reviewed seed set")

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
                raise ValueError("raster fuzz corpus seed must be a regular file")
            remaining = MAX_INPUT_BYTES
            with os.fdopen(descriptor, "rb", closefd=False) as source_file:
                with (destination / name).open("wb") as destination_file:
                    while True:
                        chunk = source_file.read(min(8192, remaining + 1))
                        if not chunk:
                            break
                        if len(chunk) > remaining:
                            raise ValueError("raster fuzz corpus seed exceeds the maximum input size")
                        destination_file.write(chunk)
                        remaining -= len(chunk)
            total_bytes += MAX_INPUT_BYTES - remaining
            if total_bytes > MAX_CORPUS_BYTES:
                raise ValueError("raster fuzz corpus exceeds the aggregate size limit")
        finally:
            os.close(descriptor)


def parse_header(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", parse_png_dimensions(data)
    if data.startswith(b"\xff\xd8"):
        return "jpeg", parse_jpeg_dimensions(data)
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        dimensions = parse_webp_raster(
            data,
            max_dimension=MAX_PNG_DIMENSION,
            max_pixels=MAX_PNG_PIXELS,
            max_total_pixels=MAX_TOTAL_PNG_PIXELS,
        )
        return "webp", dimensions
    return None


def validate_input(data):
    try:
        parsed = parse_header(data)
    except (RasterHeaderError, RasterLimitError):
        return None
    if parsed is None:
        return None
    kind, dimensions = parsed
    expected_length = 3 if kind == "webp" else 2
    if (not isinstance(dimensions, tuple) or len(dimensions) != expected_length
            or not all(type(value) is int and value > 0 for value in dimensions)):
        raise AssertionError("raster header parser returned invalid dimensions")
    width, height = dimensions[:2]
    if width > PNG_SPEC_MAX_DIMENSION or height > PNG_SPEC_MAX_DIMENSION:
        raise AssertionError("raster header parser returned dimensions above the PNG ceiling")
    if kind == "webp":
        if width > MAX_PNG_DIMENSION or height > MAX_PNG_DIMENSION:
            raise AssertionError("WebP header parser exceeded its configured dimension limit")
        if width * height > MAX_PNG_PIXELS:
            raise AssertionError("WebP header parser exceeded its per-image pixel limit")
        if dimensions[2] > MAX_TOTAL_PNG_PIXELS:
            raise AssertionError("WebP header parser exceeded its configured aggregate pixel budget")
    return kind, dimensions


def make_test_one_input():
    @atheris.instrument_func
    def test_one_input(data):
        if len(data) > MAX_INPUT_BYTES:
            return
        validate_input(data)

    return test_one_input


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: fuzz_raster_headers.py CORPUS_DIR [libFuzzer options]")
    source_corpus = Path(sys.argv[1])

    with tempfile.TemporaryDirectory(prefix="motionpack-raster-fuzz-") as temp_dir:
        temp_root = Path(temp_dir)
        corpus = temp_root / "corpus"
        corpus.mkdir()
        copy_seed_corpus(source_corpus, corpus)
        for seed_name in SEED_FILES:
            result = validate_input((corpus / seed_name).read_bytes())
            if seed_name in VALID_SEEDS and result is None:
                raise AssertionError("reviewed valid raster seed was rejected")
            if seed_name not in VALID_SEEDS and result is not None:
                raise AssertionError("reviewed invalid raster seed was accepted")

        sys.argv[1] = str(corpus)
        atheris.Setup(sys.argv, make_test_one_input())
        atheris.Fuzz()


if __name__ == "__main__":
    main()
