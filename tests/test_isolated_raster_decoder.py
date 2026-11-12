import io
import os
import pathlib
import struct
import subprocess
import tempfile
import time
import unittest
import zlib
from unittest import mock

from tools import isolated_raster_decoder as decoder
from tests.jpeg_fixtures import jpeg_with_dnl_defined_height

try:
    from PIL import Image
except ImportError:
    Image = None


@unittest.skipIf(Image is None, "optional Pillow test dependency is not installed")
class IsolatedRasterDecoderTests(unittest.TestCase):
    def image_bytes(self, image_format, *, size=(2, 1), color=(40, 80, 120, 128)):
        image = Image.new("RGBA", size, color)
        if image_format == "JPEG":
            image = image.convert("RGB")
        stream = io.BytesIO()
        image.save(stream, format=image_format)
        return stream.getvalue()

    def decode(self, data, suffix, *, limits=None, timeout=30):
        return decoder.decode_raster_assets_isolated(
            {"asset": data}, {"asset": "assets/asset" + suffix},
            limits=limits, timeout=timeout,
        )["asset"]

    def test_decodes_allowlisted_static_formats_to_rgba(self):
        for image_format, suffix in (("PNG", ".png"), ("JPEG", ".jpg"), ("WEBP", ".webp")):
            with self.subTest(image_format=image_format):
                result = self.decode(self.image_bytes(image_format), suffix)
                self.assertEqual((result.width, result.height), (2, 1))
                self.assertEqual(result.image_format, image_format)
                self.assertEqual(len(result.rgba), 2 * 1 * 4)
                if image_format == "PNG":
                    self.assertEqual(result.rgba[:4], bytes((40, 80, 120, 128)))

    def test_rejects_extension_mismatch_and_truncated_image(self):
        with self.assertRaises(decoder.RasterDecodeError):
            self.decode(self.image_bytes("PNG"), ".jpg")
        with self.assertRaises(decoder.RasterDecodeError):
            self.decode(b"\x89PNG\r\n\x1a\n", ".png")

    def test_rejects_animated_webp_in_this_api_slice(self):
        frames = [Image.new("RGBA", (1, 1), color) for color in (
            (255, 0, 0, 255), (0, 255, 0, 255),
        )]
        stream = io.BytesIO()
        frames[0].save(stream, format="WEBP", save_all=True,
                       append_images=frames[1:], duration=100, loop=0)
        with self.assertRaises(decoder.RasterDecodeError):
            self.decode(stream.getvalue(), ".webp")

    def test_animated_webp_rejection_does_not_leak_partial_worker_response(self):
        seed = pathlib.Path(__file__).parent / "fuzz_corpus" / "raster_headers" / "webp_animated.seed"
        with self.assertRaises(decoder.RasterDecodeError) as raised:
            self.decode(seed.read_bytes(), ".webp")
        self.assertNotIsInstance(raised.exception, decoder.RasterDecodeWorkerFailure)

    def test_deduplicates_aliases_of_one_validated_package_path(self):
        data = self.image_bytes("PNG")
        decoded = decoder.decode_raster_assets_isolated(
            {"one": data, "two": data},
            {"one": "assets/shared.png", "two": "assets/shared.png"},
        )
        self.assertEqual(set(decoded), {"one", "two"})
        self.assertIs(decoded["one"], decoded["two"])

    def test_rejects_aggregate_header_pixel_budget_before_worker(self):
        data = self.image_bytes("PNG")
        limits = decoder.RasterDecodeLimits(max_input_pixels=3)
        with self.assertRaises(decoder.RasterDecodeError):
            decoder.decode_raster_assets_isolated(
                {"one": data, "two": data},
                {"one": "assets/one.png", "two": "assets/two.png"},
                limits=limits,
            )

    def test_rejects_dimension_limits_before_worker(self):
        limits = decoder.RasterDecodeLimits(max_dimension=1)
        with self.assertRaises(decoder.RasterDecodeError):
            self.decode(self.image_bytes("PNG"), ".png", limits=limits)

    def test_rejects_oversized_output_from_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            script = pathlib.Path(directory) / "oversized_worker.py"
            script.write_text("import sys\nsys.stdout.buffer.write(b'X' * (2 * 1024 * 1024))\n", encoding="utf-8")
            limits = decoder.RasterDecodeLimits(max_response_bytes=1024 * 1024)
            with mock.patch.object(decoder, "WORKER_SCRIPT", script):
                with self.assertRaises(decoder.RasterDecodeResourceLimit):
                    self.decode(self.image_bytes("PNG"), ".png", limits=limits)

    def test_unexpected_worker_exception_is_not_input_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            script = pathlib.Path(directory) / "raising_worker.py"
            tools_path = pathlib.Path(decoder.__file__).resolve().parent
            script.write_text(
                "import sys\n"
                + "sys.path.insert(0, " + repr(str(tools_path)) + ")\n"
                + "import raster_decode_worker as worker\n"
                + "worker._read_request = lambda stream: ({}, [])\n"
                + "def fail(*args):\n    raise RuntimeError('injected worker error')\n"
                + "worker._write_response = fail\n"
                + "raise SystemExit(worker.main())\n",
                encoding="utf-8",
            )
            with mock.patch.object(decoder, "WORKER_SCRIPT", script):
                with self.assertRaises(decoder.RasterDecodeWorkerFailure):
                    self.decode(self.image_bytes("PNG"), ".png")

    def test_pillow_open_value_error_is_input_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            script = pathlib.Path(directory) / "open_value_error_worker.py"
            tools_path = pathlib.Path(decoder.__file__).resolve().parent
            lines = [
                "import sys",
                "sys.path.insert(0, " + repr(str(tools_path)) + ")",
                "from PIL import Image",
                "def fail(*args, **kwargs):",
                "    raise ValueError('injected open rejection')",
                "Image.open = fail",
                "import raster_decode_worker as worker",
                "raise SystemExit(worker.main())",
            ]
            script.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with mock.patch.object(decoder, "WORKER_SCRIPT", script):
                with self.assertRaises(decoder.RasterDecodeError) as raised:
                    self.decode(self.image_bytes("PNG"), ".png")
            self.assertIs(type(raised.exception), decoder.RasterDecodeError)

    def test_pillow_load_value_error_is_worker_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            script = pathlib.Path(directory) / "load_value_error_worker.py"
            tools_path = pathlib.Path(decoder.__file__).resolve().parent
            lines = [
                "import io, sys",
                "sys.path.insert(0, " + repr(str(tools_path)) + ")",
                "from PIL import Image",
                "def fail(self):",
                "    raise ValueError('injected load failure')",
                "Image.Image.load = fail",
                "import raster_decode_worker as worker",
                "real_stdout = sys.stdout",
                "class Capture:",
                "    buffer = io.BytesIO()",
                "worker.sys.stdout = Capture()",
                "worker.main()",
                "response = worker.sys.stdout.buffer.getvalue()",
                "assert response == worker.RESPONSE_MAGIC + b'\x03', response",
                "real_stdout.buffer.write(response)",
            ]
            script.write_text("\n".join(lines) + "\n", encoding="utf-8")
            with mock.patch.object(decoder, "WORKER_SCRIPT", script):
                with self.assertRaises(decoder.RasterDecodeWorkerFailure):
                    self.decode(self.image_bytes("PNG"), ".png")

    def test_worker_enforces_response_limit_before_staging(self):
        limits = decoder.RasterDecodeLimits(max_response_bytes=1)
        with self.assertRaises(decoder.RasterDecodeResourceLimit):
            self.decode(self.image_bytes("PNG"), ".png", limits=limits)

    def test_unconfirmed_windows_job_reap_retains_decoder_temp_dir(self):
        class FakeProcess:
            def __init__(self):
                self.stdin = io.BytesIO()
                self.stdout = io.BytesIO()
                self.returncode = None

            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired("decoder", timeout)

            def poll(self):
                return self.returncode

        process = FakeProcess()
        job = (123, mock.Mock())
        with tempfile.TemporaryDirectory() as parent:
            temp_path = pathlib.Path(parent) / "raster-worker"
            temp_path.mkdir()
            kill_calls = []

            def fail_job_then_kill_parent(_process, received_job=None):
                kill_calls.append(received_job)
                if received_job is not None:
                    raise TimeoutError("simulated Job Object reap failure")
                process.returncode = -9

            with mock.patch.object(decoder, "_IS_WINDOWS", True):
                with mock.patch.object(decoder.tempfile, "mkdtemp", return_value=str(temp_path)):
                    with mock.patch.object(decoder.subprocess, "Popen", return_value=process):
                        with mock.patch.object(decoder, "windows_job", return_value=job):
                            with mock.patch.object(decoder, "kill_worker", side_effect=fail_job_then_kill_parent):
                                with mock.patch.object(
                                    decoder, "read_bounded_output",
                                    side_effect=lambda _stream, _output, _overflow, _process, _limit, stop: stop.wait(),
                                ):
                                    with self.assertRaises(decoder.RasterDecodeTimeout) as raised:
                                        self.decode(self.image_bytes("PNG"), ".png", timeout=0.01)
            self.assertEqual(kill_calls, [job, None])
            self.assertTrue(temp_path.exists())
            self.assertIn(str(temp_path), raised.exception.__notes__[0])

    def test_timeout_terminates_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            script = pathlib.Path(directory) / "sleeping_worker.py"
            marker = pathlib.Path(directory) / "pid"
            script.write_text(
                "import os,time,pathlib\n"
                + "pathlib.Path(" + repr(str(marker)) + ").write_text(str(os.getpid()))\n"
                + "time.sleep(10)\n",
                encoding="utf-8",
            )
            with mock.patch.object(decoder, "WORKER_SCRIPT", script):
                with self.assertRaises(decoder.RasterDecodeTimeout):
                    self.decode(self.image_bytes("PNG"), ".png", timeout=0.2)
            self.assertTrue(marker.exists())
            if os.name != "nt":
                pid = int(marker.read_text(encoding="utf-8"))
                with self.assertRaises(ProcessLookupError):
                    os.kill(pid, 0)


class RasterDecoderInputValidationTests(unittest.TestCase):
    def test_temp_output_creation_failure_removes_temp_dir_before_worker_start(self):
        def chunk(kind, data):
            return (
                struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        png = (
            b"\x89PNG\\r\\n\x1a\\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
            + chunk(b"IEND", b"")
        )
        with tempfile.TemporaryDirectory() as parent:
            temp_dir = pathlib.Path(parent) / "raster-worker"
            with mock.patch.object(decoder.tempfile, "mkdtemp", return_value=str(temp_dir)):
                with mock.patch.object(
                    decoder.tempfile, "TemporaryFile", side_effect=OSError("injected failure")
                ):
                    with mock.patch.object(decoder.subprocess, "Popen") as popen:
                        with self.assertRaisesRegex(OSError, "injected failure"):
                            decoder.decode_raster_assets_isolated(
                                {"asset": png}, {"asset": "assets/asset.png"}
                            )
            self.assertFalse(temp_dir.exists())
            popen.assert_not_called()

    def test_rejects_dnl_defined_jpeg_height_before_starting_worker(self):
        with mock.patch.object(decoder.subprocess, 'Popen') as popen:
            with self.assertRaises(decoder.RasterDecodeError):
                decoder.decode_raster_assets_isolated(
                    {'asset': jpeg_with_dnl_defined_height()}, {'asset': 'assets/asset.jpg'}
                )
        popen.assert_not_called()

    def test_rejects_non_raster_source_and_mismatched_mapping(self):
        with self.assertRaises(ValueError):
            decoder.decode_raster_assets_isolated(
                {"asset": b"data"}, {"asset": "source/private.png"}
            )
        with self.assertRaises(ValueError):
            decoder.decode_raster_assets_isolated({"asset": b"data"}, {})

    def test_limits_are_positive_and_bounded(self):
        with self.assertRaises(ValueError):
            decoder.RasterDecodeLimits(max_dimension=0)
        with self.assertRaises(ValueError):
            decoder.RasterDecodeLimits(max_decoded_pixels=65_000_000)


if __name__ == "__main__":
    unittest.main()
