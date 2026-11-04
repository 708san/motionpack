# Security guidance

MotionPack is experimental pre-alpha software. Do not use its current tools to
open untrusted packages in a production or high-privilege environment.

The bounded reader in `tools/archive_reader.py` supports experimental v0.1/v0.2
packages. It checks ZIP member names and metadata, enforces configurable size
and compression-ratio limits, and reads only the manifest and referenced image
assets. It does not extract arbitrary ZIP members. Optional `source/` entries
are not decompressed, inspected for secrets, or returned by the reader.
The default reader limits are 40 MiB per archive, 1,024 entries, 2 MiB for the
central directory, 1 MiB for the manifest, 12 MiB per asset, 32 MiB total
referenced assets, 40 MiB total declared expansion, and a 100:1 compression
ratio. These are configurable tool defaults, not format-wide limits. ZIP64 and
multi-disk archives are rejected.

For asset paths ending in `.png` (case-insensitively), the validator and reader
inspect the PNG signature and first IHDR chunk before any decoder is involved.
PNG data stored under another extension is not detected by this check. Default
tool ceilings are 8,192 pixels per edge,
16,000,000 pixels per referenced PNG and 64,000,000 pixels total across
distinct referenced PNG paths or archive entries. The IHDR CRC is checked,
but later chunks and image data are not parsed or decoded. These are tool
acceptance limits, not format-wide rules, and they do not protect a later
decoder from malformed image data. Current tools may reject older v0.1/v0.2
packages over these ceilings despite no schema or format-version change. JPEG
and WebP dimension limits are not yet implemented. Reader callers can adjust
the tool ceilings; the PNG specification's 2^31−1 maximum dimension is always
enforced.

This reader is not a sandbox or a production security guarantee. The validator
now rejects XML DTDs/entities, foreign namespaces, unsafe SVG attributes and
external CSS/URL references, and bounds SVG nesting, element count, attributes
per element and attribute values. It permits only a local `url(#id)` gradient reference in
`fill` or `stroke`. This is a limited static SVG subset check, not a sanitizer
for arbitrary renderers. Raster image decoders are not isolated, and the
standard-library ZIP parser has only a small deterministic mutation smoke test;
it has not had sustained or coverage-guided fuzzing and is not isolated.
CPU/time limits have not been independently measured. Keep packages and their
assets untrusted.

The project packager emits only `manifest.json` and its referenced runtime
assets; it does not automatically add unreferenced project files or `source/`.
The validator rejects runtime references into `source/` and local project paths
with symlink components. The packager snapshots the bounded asset bytes used by
validation and uses those same bytes for the ZIP and preview. It does not scan
the contents or metadata of explicitly referenced assets for secrets, so
maintainers must review those assets before distribution.

On platforms that support directory-relative no-follow opens, each project
path component is opened beneath a pinned directory. Other platforms recheck
path components and file identity, but cannot fully rule out every concurrent
directory replacement. Build from a project tree that is not being changed by
another process.

If a security issue is discovered, contact the repository maintainer privately
through an access-controlled channel; do not publish exploit details in a
public Issue. A dedicated vulnerability contact has not been designated.
