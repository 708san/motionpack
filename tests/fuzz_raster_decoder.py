#!/usr/bin/env python3
"""Coverage-guided fuzz target for the process-isolated raster decoder."""
from io import BytesIO
from pathlib import Path
import shutil
import sys
import tempfile

import atheris
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

with atheris.instrument_imports():
    import isolated_raster_decoder as decoder

from fuzz_raster_headers import SEED_FILES, copy_seed_corpus

MAX_INPUT_BYTES = 64 * 1024
MAX_CORPUS_FILES = 16
MAX_CORPUS_BYTES = 1024 * 1024
MAX_DIMENSION = 512
MAX_PIXELS = MAX_DIMENSION * MAX_DIMENSION
STATIC_REJECTION_SEEDS = (
    "png_bad_crc.seed",
    "png_truncated.seed",
    "jpeg_bad_segment.seed",
    "jpeg_without_frame.seed",
    "webp_animated.seed",
    "webp_bad_bounds.seed",
)
FORMATS = {
    b"\x89PNG\r\n\x1a\n": (".png", "PNG"),
    b"\xff\xd8": (".jpg", "JPEG"),
    b"RIFF": (".webp", "WEBP"),
}


def make_valid_image(image_format):
    image = Image.new("RGBA", (2, 1), (40, 80, 120, 128))
    if image_format == "JPEG":
        image = image.convert("RGB")
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def image_kind(data):
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return FORMATS[b"RIFF"]
    for signature, result in FORMATS.items():
        if signature != b"RIFF" and data.startswith(signature):
            return result
    return None


LIMITS = decoder.RasterDecodeLimits(
    max_dimension=MAX_DIMENSION,
    max_image_pixels=MAX_PIXELS,
    max_input_pixels=MAX_PIXELS,
    max_decoded_pixels=MAX_PIXELS,
    max_asset_bytes=MAX_INPUT_BYTES,
    max_total_asset_bytes=MAX_INPUT_BYTES,
    max_assets=1,
    max_response_bytes=MAX_PIXELS * 4 + 64 * 1024,
)


def validate_input(data):
    if len(data) > MAX_INPUT_BYTES:
        return None
    kind = image_kind(data)
    if kind is None:
        return None
    suffix, expected_format = kind
    try:
        decoded = decoder.decode_raster_assets_isolated(
            {"fuzz": data},
            {"fuzz": "assets/fuzz" + suffix},
            limits=LIMITS,
            timeout=1.8,
        )
    except (decoder.RasterDecodeWorkerFailure, decoder.RasterDecodeTimeout) as error:
        raise AssertionError("isolated raster worker failed on fuzz input") from error
    except decoder.RasterDecodeError:
        return None

    if set(decoded) != {"fuzz"}:
        raise AssertionError("isolated decoder returned unexpected asset IDs")
    image = decoded["fuzz"]
    if (image.image_format != expected_format
            or type(image.width) is not int or type(image.height) is not int
            or not 1 <= image.width <= MAX_DIMENSION
            or not 1 <= image.height <= MAX_DIMENSION
            or image.width * image.height > MAX_PIXELS
            or not isinstance(image.rgba, bytes)
            or len(image.rgba) != image.width * image.height * 4):
        raise AssertionError("isolated decoder returned an invalid bounded RGBA image")
    return image


def make_test_one_input():
    @atheris.instrument_func
    def test_one_input(data):
        validate_input(data)

    return test_one_input


def prepare_corpus(source, corpus):
    # Reuse the existing exact-name, no-follow, regular-file and byte-limit
    # checks for the reviewed raster-header corpus before selecting seeds.
    staged = corpus.parent / "reviewed-header-corpus"
    staged.mkdir()
    copy_seed_corpus(source, staged)
    for name in STATIC_REJECTION_SEEDS:
        shutil.copyfile(staged / name, corpus / name)
    for suffix, image_format in ((".png", "PNG"), (".jpg", "JPEG"), (".webp", "WEBP")):
        (corpus / ("valid" + suffix + ".seed")).write_bytes(make_valid_image(image_format))
    shutil.rmtree(staged)

    entries = list(corpus.iterdir())
    if len(entries) > MAX_CORPUS_FILES:
        raise ValueError("decoder fuzz corpus exceeds the reviewed file-count limit")
    total_bytes = 0
    for entry in entries:
        if not entry.is_file() or entry.is_symlink():
            raise ValueError("decoder fuzz seed must be a regular file")
        size = entry.stat().st_size
        if size > MAX_INPUT_BYTES:
            raise ValueError("decoder fuzz seed exceeds the maximum input size")
        total_bytes += size
    if total_bytes > MAX_CORPUS_BYTES:
        raise ValueError("decoder fuzz corpus exceeds the aggregate size limit")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: fuzz_raster_decoder.py HEADER_CORPUS_DIR [libFuzzer options]")
    source_corpus = Path(sys.argv[1])

    with tempfile.TemporaryDirectory(prefix="motionpack-raster-decoder-fuzz-") as temp_dir:
        corpus = Path(temp_dir) / "corpus"
        corpus.mkdir()
        prepare_corpus(source_corpus, corpus)

        for suffix, image_format in ((".png", "PNG"), (".jpg", "JPEG"), (".webp", "WEBP")):
            result = validate_input((corpus / ("valid" + suffix + ".seed")).read_bytes())
            if result is None or result.image_format != image_format:
                raise AssertionError("reviewed valid raster seed was rejected")
        for name in STATIC_REJECTION_SEEDS:
            try:
                result = validate_input((corpus / name).read_bytes())
            except AssertionError as error:
                raise AssertionError("reviewed raster rejection seed failed: " + name) from error
            if result is not None:
                raise AssertionError("reviewed invalid raster seed was accepted: " + name)

        sys.argv[1] = str(corpus)
        atheris.Setup(sys.argv, make_test_one_input())
        atheris.Fuzz()


if __name__ == "__main__":
    main()
