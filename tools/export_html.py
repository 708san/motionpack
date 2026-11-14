#!/usr/bin/env python3
"""Export a validated legacy MotionPack ZIP as an offline, single-file HTML preview.

This is a playback export, not a migration to the unfinished v1 format.
"""
import argparse
import base64
import json
import mimetypes
from pathlib import Path
import sys

try:
    from .archive_reader import ArchiveError, read_package
    from .package import render_preview_html, _redact_secret_like_text
except ImportError:
    from archive_reader import ArchiveError, read_package
    from package import render_preview_html, _redact_secret_like_text

MAX_HTML_BYTES = 64 * 1024 * 1024


def export_html(archive_path, output_path):
    """Embed only referenced, validated assets into the canonical offline player.

    The isolated reader limits ZIP parsing; it is defense in depth, not a sandbox.
    Never follow output paths for archives or extract source/ contents to disk.
    The destination must not already exist.
    """
    source = Path(archive_path)
    dest = Path(output_path)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError("HTML output already exists")
    if not dest.parent.is_dir():
        raise ValueError("HTML output parent directory does not exist")

    package = read_package(source)
    embedded = json.loads(json.dumps(package.manifest))
    for asset_id, relative_path in package.manifest["assets"].items():
        mime = mimetypes.guess_type(relative_path)[0]
        if mime not in ("image/svg+xml", "image/png", "image/jpeg", "image/webp"):
            raise ValueError("unsupported preview asset type")
        payload = package.assets[asset_id]
        embedded["assets"][asset_id] = (
            "data:" + mime + ";base64," + base64.b64encode(payload).decode("ascii")
        )
    html_bytes = render_preview_html(embedded).encode("utf-8")
    if len(html_bytes) > MAX_HTML_BYTES:
        raise ValueError("embedded HTML exceeds 64 MiB limit")
    created = False
    try:
        with dest.open("xb") as stream:
            created = True
            stream.write(html_bytes)
    except Exception:
        if created:
            dest.unlink(missing_ok=True)
        raise
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export a .motionpack to offline playable HTML")
    parser.add_argument("archive", help="input .motionpack archive (experimental v0.1-v0.4)")
    parser.add_argument("--out", required=True, help="new HTML output path (will not overwrite)")
    args = parser.parse_args()
    try:
        result = export_html(args.archive, args.out)
    except (OSError, ValueError, TypeError, ArchiveError) as exc:
        print("HTML export failed: " + _redact_secret_like_text(exc), file=sys.stderr)
        sys.exit(1)
    print("Created:", result, result.stat().st_size, "bytes")
