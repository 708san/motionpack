#!/usr/bin/env python3
"""Collect report-only package and archive-reader measurements for Issue #5."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
READER_SAMPLES = 30


def percentile(values, fraction):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def measure_reader_process(archive):
    sys.path.insert(0, str(ROOT / "tools"))
    from archive_reader import read_package

    read_package(archive)
    durations = []
    for _ in range(READER_SAMPLES):
        started = time.perf_counter()
        read_package(archive)
        durations.append((time.perf_counter() - started) * 1000)

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel32.GetCurrentProcess()
        get_memory_info = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        get_memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
        get_memory_info.restype = wintypes.BOOL
        if not get_memory_info(process, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        peak_bytes = int(counters.PeakWorkingSetSize)
    else:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak_bytes = int(peak if sys.platform == "darwin" else peak * 1024)
    return {
        "sample_count": len(durations),
        "warmup_samples": 1,
        "median_ms": statistics.median(durations),
        "p95_ms": percentile(durations, 0.95),
        "samples_ms": durations,
        "peak_process_rss_bytes": peak_bytes,
        "peak_rss_includes_interpreter": True,
    }


def reader_subprocess(archive):
    completed = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--reader-child", str(archive)],
        check=True,
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=20,
    )
    return json.loads(completed.stdout)


def collect(output):
    sys.path.insert(0, str(ROOT / "tools"))
    from package import build

    from validate import validate

    output.mkdir(parents=True, exist_ok=True)
    package_dir = output / "package"
    package_dir.mkdir(parents=True, exist_ok=True)
    build_started = time.perf_counter()
    archive, preview = build(ROOT / "examples" / "robot_ik_demo", package_dir)
    build_ms = (time.perf_counter() - build_started) * 1000
    errors, _ = validate(ROOT / "examples" / "robot_ik_demo")
    if errors:
        raise ValueError("v0.2 benchmark example failed validation: " + "; ".join(errors))

    frozen_v01 = ROOT / "tests" / "fuzz_corpus" / "archive_reader" / "valid_v01.motionpack"
    fixtures = {
        "v0.1_frozen": (frozen_v01, "tests/fuzz_corpus/archive_reader/valid_v01.motionpack"),
        "v0.2_generated": (archive, "examples/robot_ik_demo (generated for measurement)"),
    }
    fixture_results = {}
    for name, (fixture, fixture_label) in fixtures.items():
        payload = fixture.read_bytes()
        fixture_results[name] = {
            "path": fixture_label,
            "archive_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "archive_reader": reader_subprocess(fixture),
        }

    report = {
        "schema_version": 1,
        "measurement_kind": "report-only; no performance thresholds",
        "environment": {
            "os": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "cpu_count_logical": os.cpu_count(),
        },
        "definitions": {
            "package_build_ms": "Wall-clock time for tools.package.build() on examples/robot_ik_demo, including validation and preview generation.",
            "archive_reader": "One warm-up read followed by 30 sequential read_package() timing samples in one fresh Python process per archive; p95 uses the nearest-rank definition and samples share filesystem cache state.",
            "collection_timeout_seconds": "Playwright allows 120 seconds for the complete benchmark test; a timeout means collection failed, not that a performance value exceeded a threshold.",
            "reader_subprocess_timeout_seconds": "Each fresh archive-reader process has a 20-second subprocess deadline.",
            "peak_process_rss_bytes": "Process high-water resident memory after reader samples: getrusage ru_maxrss on Unix and PeakWorkingSetSize on Windows. Includes Python interpreter and module baseline; excludes the parent process. OS methods are not directly comparable.",
            "browser_load_to_images_ready_ms": "Playwright wall-clock from before file navigation until every embedded image reports complete with nonzero naturalWidth.",
            "frame_interval_ms": "Real browser requestAnimationFrame timestamp differences after a 30-frame warm-up; interval includes browser scheduling and page work, not isolated Canvas draw time.",
        },
        "package_build_ms": build_ms,
        "package_bytes": archive.stat().st_size,
        "preview_bytes": preview.stat().st_size,
        "fixtures": fixture_results,
        "browser": None,
    }
    numeric_values = [report["package_build_ms"], report["package_bytes"], report["preview_bytes"]]
    for fixture in fixture_results.values():
        numeric_values.extend((fixture["archive_bytes"], fixture["archive_reader"]["median_ms"],
                               fixture["archive_reader"]["p95_ms"],
                               fixture["archive_reader"]["peak_process_rss_bytes"]))
        numeric_values.extend(fixture["archive_reader"]["samples_ms"])
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
           for value in numeric_values):
        raise ValueError("performance report contains an invalid numeric value")
    if any(fixture["archive_reader"]["sample_count"] != READER_SAMPLES
           or fixture["archive_reader"]["warmup_samples"] != 1
           for fixture in fixture_results.values()):
        raise ValueError("performance report has an incomplete reader sample set")
    destination = output / "performance.json"
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--reader-child", type=Path)
    args = parser.parse_args()
    if args.reader_child:
        print(json.dumps(measure_reader_process(args.reader_child)))
    elif args.out:
        collect(args.out.resolve())
    else:
        parser.error("provide --out or --reader-child")


if __name__ == "__main__":
    main()
