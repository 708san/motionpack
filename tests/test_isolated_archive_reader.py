import errno
import hashlib
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

from archive_reader import ArchiveError, ReaderLimits, read_package
from isolated_archive_reader import _snapshot_archive
from isolated_archive_reader import (
    IsolatedReadTimeout,
    IsolatedResourceLimit,
    UnsupportedMemoryLimit,
    read_package_isolated,
)


class IsolatedArchiveReaderTests(unittest.TestCase):
    def _valid_fixture(self, folder, version):
        fixture_dir = "fuzz_corpus/archive_reader" if version in ("0.1", "0.2") else "fixtures/compatibility_archive_reader"
        seed = ROOT / "tests" / fixture_dir / f"valid_v{version.replace('.', '')}.motionpack"
        if version == "0.2":
            self.assertEqual(
                hashlib.sha256(seed.read_bytes()).hexdigest(),
                "ffc5bc6c3a4d4531c41c925a70e943dcd111b17b7f674527247079fdd626fbad",
                "update the frozen v0.2 fixture hash only with an explicit compatibility review",
            )
        target = pathlib.Path(folder) / f"valid-v{version}.motionpack"
        shutil.copyfile(seed, target)
        return target

    def _input_file(self, folder):
        path = pathlib.Path(folder) / "input.motionpack"
        path.write_bytes(b"test input")
        return path

    def _fake_worker(self, folder, body):
        worker = pathlib.Path(folder) / "fake_worker.py"
        worker.write_text(
            "import json, struct, sys\n"
            "stream = sys.stdin.buffer\n"
            "if stream.read(1) != b'G': raise SystemExit(2)\n"
            "size = struct.unpack('!I', stream.read(4))[0]\n"
            "request = json.loads(stream.read(size).decode('utf-8'))\n"
            + body,
            encoding="utf-8",
        )
        return worker

    def _assert_pid_exited(self, pid):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel32.OpenProcess.restype = wintypes.HANDLE
                kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
                kernel32.WaitForSingleObject.restype = wintypes.DWORD
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                handle = kernel32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
                if not handle:
                    error = ctypes.get_last_error()
                    if error == 87:  # ERROR_INVALID_PARAMETER: process ID no longer exists.
                        return
                    raise AssertionError(f"could not query worker process {pid}: {error}")
                state = kernel32.WaitForSingleObject(handle, 0)
                kernel32.CloseHandle(handle)
                if state == 0:  # WAIT_OBJECT_0
                    return
                if state != 258:  # WAIT_TIMEOUT
                    raise AssertionError(f"unexpected worker wait result: {state}")
            else:
                try:
                    os.kill(pid, 0)
                except OSError as exc:
                    if exc.errno == errno.ESRCH:
                        return
                    raise
                try:
                    state = subprocess.run(
                        ["ps", "-o", "stat=", "-p", str(pid)],
                        capture_output=True, text=True, timeout=1, check=False,
                    ).stdout.strip()
                    if not state or state.startswith("Z"):
                        return
                except (OSError, subprocess.SubprocessError):
                    pass
            time.sleep(0.05)
        self.fail("isolated worker remains alive after wrapper returned")

    def test_reads_v01_through_v04_packages(self):
        with tempfile.TemporaryDirectory() as tmp:
            for version in ("0.1", "0.2", "0.3", "0.4"):
                with self.subTest(version=version):
                    archive = self._valid_fixture(tmp, version)
                    direct_result = read_package(archive)
                    self.assertEqual(direct_result.manifest["version"], version)
                    snapshot = pathlib.Path(tmp) / f"snapshot-v{version}.motionpack"
                    _snapshot_archive(archive, snapshot, ReaderLimits())
                    snapshot_result = read_package(snapshot)
                    self.assertEqual(snapshot_result.manifest["version"], version)
                    result = read_package_isolated(archive, timeout=20)
                    self.assertEqual(result.manifest["version"], version)
                    self.assertEqual(set(result.assets), set(result.manifest["assets"]))
                    self.assertTrue(all(isinstance(data, bytes) for data in result.assets.values()))
                    retained = read_package(archive, include_entries=True)
                    isolated_retained = read_package_isolated(
                        archive, timeout=20, include_entries=True
                    )
                    self.assertEqual(retained.manifest_bytes, isolated_retained.manifest_bytes)
                    self.assertEqual(retained.entries, isolated_retained.entries)
                    self.assertEqual(retained.source_entries, isolated_retained.source_entries)

    def test_snapshot_rejects_different_regular_file_opened_after_stat(self):
        with tempfile.TemporaryDirectory() as tmp:
            checked = self._valid_fixture(tmp, "0.1")
            opened = self._valid_fixture(tmp, "0.2")
            opened = opened.with_name("opened.motionpack")
            source = self._valid_fixture(tmp, "0.2")
            shutil.copyfile(source, opened)
            destination = pathlib.Path(tmp) / "snapshot.motionpack"
            original_stat = type(opened).stat

            def report_checked_identity(path, *args, **kwargs):
                return original_stat(checked if path == opened else path, *args, **kwargs)

            with mock.patch.object(
                type(opened), "stat", autospec=True, side_effect=report_checked_identity
            ):
                with self.assertRaisesRegex(ArchiveError, "archive input changed between stat and open"):
                    _snapshot_archive(opened, destination, ReaderLimits())
            self.assertFalse(destination.exists())

    def test_regular_file_symlink_input_remains_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            package = self._valid_fixture(tmp, "0.1")
            alias = pathlib.Path(tmp) / "regular-file-link.motionpack"
            try:
                alias.symlink_to(package)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"regular-file symlinks are unavailable: {exc}")

            self.assertEqual(read_package_isolated(alias, timeout=20).manifest["version"], "0.1")
            snapshot = pathlib.Path(tmp) / "snapshot.motionpack"
            _snapshot_archive(alias, snapshot, ReaderLimits())
            self.assertEqual(read_package(snapshot).manifest["version"], "0.1")

    def test_snapshot_rejects_unavailable_file_identity_before_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._valid_fixture(tmp, "0.1")
            destination = pathlib.Path(tmp) / "snapshot.motionpack"
            with mock.patch("isolated_archive_reader._file_identity", return_value=None):
                with mock.patch(
                    "isolated_archive_reader.os.open",
                    side_effect=AssertionError("must fail before open"),
                ):
                    with self.assertRaisesRegex(ArchiveError, "identity cannot be verified"):
                        _snapshot_archive(source, destination, ReaderLimits())
            self.assertFalse(destination.exists())

    def test_rejects_malformed_archive_with_archive_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = pathlib.Path(tmp) / "bad.motionpack"
            archive.write_bytes(b"not a zip")
            with self.assertRaises(ArchiveError):
                read_package_isolated(archive)

    def test_timeout_kills_and_reaps_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = pathlib.Path(tmp) / "worker-pids.txt"
            worker = self._fake_worker(
                tmp,
                "import os, pathlib, subprocess, sys, time\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()) + ' ' + str(child.pid))\n"
                "time.sleep(30)\n",
            )
            with mock.patch("isolated_archive_reader.WORKER_SCRIPT", worker):
                with self.assertRaises(IsolatedReadTimeout):
                    read_package_isolated(self._input_file(tmp), timeout=2)
            for pid in map(int, pid_file.read_text().split()):
                self._assert_pid_exited(pid)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO support")
    def test_snapshot_rejects_fifo_and_fifo_symlink_before_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            fifo = pathlib.Path(tmp) / "input.motionpack"
            os.mkfifo(fifo)
            alias = pathlib.Path(tmp) / "input-link.motionpack"
            alias.symlink_to(fifo)
            destination = pathlib.Path(tmp) / "snapshot.motionpack"
            with mock.patch(
                "isolated_archive_reader.os.open",
                side_effect=AssertionError("must reject special file before open"),
            ):
                for candidate in (fifo, alias):
                    with self.subTest(candidate=candidate):
                        with self.assertRaisesRegex(ArchiveError, "regular file"):
                            _snapshot_archive(candidate, destination, ReaderLimits())
            self.assertFalse(destination.exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO support")
    def test_deadline_interrupts_a_worker_blocked_opening_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            fifo = pathlib.Path(tmp) / "blocked.motionpack"
            os.mkfifo(fifo)
            pid_file = pathlib.Path(tmp) / "worker.pid"
            worker = self._fake_worker(
                tmp,
                "import os, pathlib\n"
                f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
                "open(request['path'], 'rb').read()\n",
            )
            with mock.patch("isolated_archive_reader.WORKER_SCRIPT", worker):
                with self.assertRaises(IsolatedReadTimeout):
                    read_package_isolated(fifo, timeout=1.5)
            self._assert_pid_exited(int(pid_file.read_text()))

    def test_oversized_worker_response_is_stopped(self):
        limits = ReaderLimits(max_manifest_bytes=1, max_total_assets_bytes=1)
        with tempfile.TemporaryDirectory() as tmp:
            pid_file = pathlib.Path(tmp) / "worker.pid"
            worker = self._fake_worker(
                tmp,
                "import os, pathlib, time\n"
                f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
                "sys.stdout.buffer.write(b'X' * 70000); sys.stdout.buffer.flush()\n"
                "time.sleep(30)\n",
            )
            with mock.patch("isolated_archive_reader.WORKER_SCRIPT", worker):
                with self.assertRaises(IsolatedResourceLimit):
                    read_package_isolated(
                        self._input_file(tmp),
                        limits=limits, timeout=5,
                    )
            self._assert_pid_exited(int(pid_file.read_text()))

    @unittest.skipIf(sys.platform == "darwin", "macOS hard memory limits are explicitly unsupported")
    @unittest.skipUnless(sys.platform.startswith("linux") or os.name == "nt", "no enforced memory limit on this OS")
    def test_memory_limit_is_applied_in_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            worker = self._fake_worker(
                tmp,
                "import os, sys\n"
                "if sys.platform.startswith('linux'):\n"
                " import resource\n"
                " req_limit = request['memory_limit_bytes']\n"
                " _, hard = resource.getrlimit(resource.RLIMIT_AS)\n"
                " if hard != resource.RLIM_INFINITY: req_limit = min(req_limit, hard)\n"
                " resource.setrlimit(resource.RLIMIT_AS, (req_limit, req_limit))\n"
                "try: bytearray(1024 * 1024 * 1024)\n"
                "except MemoryError:\n"
                " sys.stdout.buffer.write(b'MPIR\\x02\\x03'); sys.stdout.buffer.flush(); raise SystemExit(0)\n"
                "raise SystemExit(7)\n",
            )
            with mock.patch("isolated_archive_reader.WORKER_SCRIPT", worker):
                with self.assertRaises(IsolatedResourceLimit):
                    read_package_isolated(
                        self._input_file(tmp),
                        timeout=20, memory_limit_bytes=512 * 1024 * 1024,
                    )

    @unittest.skipUnless(sys.platform == "darwin", "macOS policy check")
    def test_mac_os_rejects_explicit_hard_memory_limit(self):
        with self.assertRaises(UnsupportedMemoryLimit):
            read_package_isolated("unused.motionpack", memory_limit_bytes=512 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
