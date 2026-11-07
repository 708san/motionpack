#!/usr/bin/env python3
"""Run the report collector with a cross-platform wall-clock deadline."""
import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
COLLECTOR_TIMEOUT_SECONDS = 60


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    subprocess.run(
        [sys.executable, str(ROOT / "tests" / "performance_report.py"),
         "--out", str(args.out)],
        check=True,
        cwd=ROOT,
        timeout=COLLECTOR_TIMEOUT_SECONDS,
    )


if __name__ == "__main__":
    main()
