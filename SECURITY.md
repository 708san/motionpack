# Security guidance

MotionPack is experimental pre-alpha software. Do not use its current tools to
open untrusted packages in a production or high-privilege environment.

The bounded reader in `tools/archive_reader.py` supports experimental v0.1/v0.2/v0.3
packages. It checks ZIP member names and metadata, enforces configurable size
and compression-ratio limits, and reads only the manifest and referenced image
assets. It does not extract arbitrary ZIP members. Optional `source/` entries
are not decompressed, inspected for secrets, or returned by the reader.
The default reader limits are 40 MiB per archive, 1,024 entries, 2 MiB for the
central directory, 1 MiB for the manifest, 12 MiB per asset, 32 MiB total
referenced assets, 40 MiB total declared expansion, and a 100:1 compression
ratio. These are configurable tool defaults, not format-wide limits. ZIP64 and
multi-disk archives are rejected.

Before opening an archive path, the reader checks that it currently resolves to
a regular file, then checks the opened descriptor again. It uses
`O_NONBLOCK` where the operating system exposes that flag. The path check and
open are separate operations, so a concurrently replaced path may still be
opened before the descriptor check rejects it. Python exposes `O_NONBLOCK` on
Unix. On a platform that lacks the flag and supports blocking special-file
types, a path replaced with such a file after the initial check may block
during open. Windows behavior has not been tested. This reader does not
guarantee safe handling of paths that another process can change concurrently.

For asset paths ending in `.png`, `.jpg`, `.jpeg`, or `.webp` (case-insensitively),
the validator and reader inspect the corresponding format header before any
decoder is involved. The default tool ceilings are 8,192 pixels per edge,
16,000,000 pixels per referenced raster image and 64,000,000 pixels total across
distinct referenced PNG/JPEG/WebP paths or archive entries. PNG inspection checks
the signature, IHDR framing and CRC; JPEG inspection scans marker segments only
through the first frame header; WebP inspection reads the RIFF image or canvas
header. For animated WebP, the reader also checks each ANMF frame region and
bitstream header, and counts the canvas area plus all frame areas against the
shared aggregate budget. JPEG height defined later by DNL is unsupported. These
checks do not decode image data, and do not detect the actual media format
independently of its filename extension. They are
tool acceptance limits, not format-wide rules, and do not protect a later decoder
from malformed data. Current tools may reject older v0.1/v0.2 packages over these
ceilings despite no schema or format-version change. Reader callers can adjust
the tool ceilings with `max_raster_*` settings. Existing `max_png_*` settings
remain accepted as aliases when the corresponding raster setting is omitted.
The PNG specification's 2^31−1 maximum dimension is always enforced.

For v0.3, SVG root `width` and `height` are required positive numeric px values.
The format maxima are 8,192 px per edge and 16,000,000 px per SVG; validator
and reader settings may lower these limits but cannot raise them. Versions
v0.1/v0.2 retain their previous behavior and may omit these dimensions.

This reader is not a sandbox or a production security guarantee. The validator
now rejects XML DTDs/entities, foreign namespaces, unsafe SVG attributes and
external CSS/URL references, rejects attributes outside the documented
element-specific allowlists, and bounds SVG nesting, element count, attributes
per element and attribute values. Attribute values are not checked against every
SVG value grammar. It permits only a local `url(#id)` gradient reference in
`fill` or `stroke`. This is a limited static SVG subset check, not a sanitizer
for arbitrary renderers. Raster image decoders are not isolated. Bounded
Atheris coverage-guided targets exercise the ZIP reader, SVG validator, and
raster header parsers, each with a 15-second pull-request run and a 300-second
weekly/manual campaign.
Inputs are capped at 64 KiB, each case has a 2-second timeout, and the shared
job has a 20-minute limit. This remains bounded fuzzing, not continuous fuzzing. The default
`read_package()` path remains in-process; the opt-in wrapper below uses
platform-specific process and memory controls and is not a sandbox. Keep
packages and their assets untrusted.

## Opt-in isolated reader

`tools/isolated_archive_reader.py` provides `read_package_isolated()` as a
separate, opt-in API; the existing synchronous `read_package()` behavior is
unchanged. The wrapper creates a private temporary directory and starts a fresh
Python worker without a shell. The worker snapshots at most 40 MiB of a regular
input file there, then reads the snapshot. The parent enforces the deadline
across input open/copy and ZIP inspection, and counts process creation and job
setup against the available time. Process creation and OS job setup are
synchronous and cannot themselves be interrupted; after they return, an expired
deadline causes immediate worker termination. A blocked special-file open is
covered by the child-process timeout. The fixed binary response protocol is
capped at 40 MiB. The default wall-clock deadline is 30 seconds and callers may
set a deadline up to 300 seconds. A timeout or oversized result terminates and
reaps the worker. POSIX uses a new process session and kills its process group;
Windows assigns the waiting worker to a Job Object configured to terminate its
processes when the job closes.

The default memory policy is OS-specific:

- Linux applies a 512 MiB `RLIMIT_AS` address-space ceiling in the worker before
  it opens the snapshot. This is a virtual-address limit, not a resident-memory
  or cgroup limit.
- Windows applies a 512 MiB per-process committed-memory limit using a Job
  Object before sending the worker its request.
- macOS has no supported whole-process hard memory limit in this implementation.
  The wrapper still enforces its timeout and protocol bounds there. An explicit
  positive `memory_limit_bytes` request raises `UnsupportedMemoryLimit` on macOS.

`memory_limit_bytes=0` disables an available OS memory limit; a positive custom
value requests a limit and fails closed on platforms where this implementation
cannot enforce one. The default `None` selects the platform policy above. A
Linux worker may fail to start parsing if its Python runtime cannot fit within
the configured address-space ceiling. A Windows Job Object assignment failure
also fails closed before the worker receives input. Platform limits include
runtime overhead and may need adjustment for callers with different archive
limits.

The wrapper reduces exposure to parser hangs and unbounded protocol output; it
does not sandbox the worker. The worker runs under the caller's account, can
access files and network resources available to that account, and may still be
affected by OS/runtime vulnerabilities. The snapshot's path check and open are
not atomic on every platform. POSIX process-group cleanup does not contain a
process that deliberately detaches into a new session. No hostile raster
decoder is launched. The three-OS CI matrix verifies the wrapper's API and
timeout behavior; Linux and Windows also exercise their
memory-limit mechanisms. macOS CI verifies the documented unsupported-memory
behavior rather than claiming a hard cap.

The target and synthetic seed corpus are in `tests/fuzz_archive_reader.py`
and `tests/fuzz_corpus/archive_reader/`. It accepts only the six reviewed
regular-file seeds, caps the corpus at 16 files / 1 MiB and each seed at
64 KiB, and copies them to a temporary directory before fuzzing so direct
invocation cannot mutate the checked-in corpus. It exercises
`read_package(path)` and accepts only `ArchiveError` as an expected rejection;
unexpected exceptions or inconsistent successful results fail the run. On Linux x86-64 with CPython
3.12, install the hash-pinned test-only dependency and run a local budget with:

```sh
python3.12 -m venv /tmp/motionpack-fuzz-venv
/tmp/motionpack-fuzz-venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements-fuzz.txt
mkdir -p /tmp/motionpack-fuzz-artifacts
/tmp/motionpack-fuzz-venv/bin/python tests/fuzz_archive_reader.py tests/fuzz_corpus/archive_reader -max_total_time=300 -timeout=2 -max_len=65536 -rss_limit_mb=1024 -seed=317770 -artifact_prefix=/tmp/motionpack-fuzz-artifacts/
```

The SVG validator target is `tests/fuzz_svg_validator.py` with reviewed seeds in
`tests/fuzz_corpus/svg_validator/`. It applies the same corpus, input, timeout,
and memory ceilings, and treats malformed XML or validator rejection as
expected input outcomes. Unexpected exceptions or invalid return shapes fail
the run. Run it locally with the same environment and budget:

```sh
/tmp/motionpack-fuzz-venv/bin/python tests/fuzz_svg_validator.py tests/fuzz_corpus/svg_validator -max_total_time=300 -timeout=2 -max_len=65536 -rss_limit_mb=1024 -seed=317771 -artifact_prefix=/tmp/motionpack-fuzz-artifacts/svg-
```

The raster header target is `tests/fuzz_raster_headers.py` with reviewed PNG,
JPEG, and WebP seeds in `tests/fuzz_corpus/raster_headers/`. It exercises only
dimension/header parsing; it does not decode image pixels or test downstream
image decoders. It accepts the 16 reviewed regular-file seeds only, limits the
corpus to 16 files / 1 MiB and each seed to 64 KiB, and copies inputs to a
temporary directory. Malformed or over-limit headers use explicit raster
rejection exception types; unexpected exceptions fail the run. Run it locally
with:

```sh
/tmp/motionpack-fuzz-venv/bin/python tests/fuzz_raster_headers.py tests/fuzz_corpus/raster_headers -max_total_time=300 -timeout=2 -max_len=65536 -rss_limit_mb=1024 -seed=317772 -artifact_prefix=/tmp/motionpack-fuzz-artifacts/raster-
```

Atheris is test-only and does not enter the runtime package. Version 3.1.0 is
pinned to the Linux CPython 3.12 wheel hash; the upstream project is Apache-2.0.
PyPI lists no provenance attestation for this release, so the workflow uses a
hash-locked wheel in an isolated environment, with read-only repository
permissions and no secrets. Review generated crash inputs before adding them
as regression fixtures; the workflow does not upload or commit fuzz outputs.

The project packager emits only `manifest.json` and its referenced runtime
assets; it does not automatically add unreferenced project files or `source/`.
The validator rejects runtime references into `source/` and local project paths
with symlink components. The packager snapshots the bounded asset bytes used by
validation and uses those same bytes for the ZIP and preview. It scans raw
referenced-asset bytes for a small set of private-key headers and GitHub,
OpenAI, and AWS credential-like patterns, then prints the 1-based
referenced-asset ordinal and category to standard error without printing the
path or matched value. By default, this is warning-only and matching
bytes remain in the ZIP and preview. Pass `--fail-on-secret-like` to reject a
match before creating or replacing either output. The opt-in mode can reject
legitimate assets that match a heuristic. Scanning can miss transformed or
pixel-encoded secrets and can produce false positives; maintainers must review
assets before distribution.

On platforms that support directory-relative no-follow opens, each project
path component is opened beneath a pinned directory. Other platforms recheck
path components and file identity, but cannot fully rule out every concurrent
directory replacement. Build from a project tree that is not being changed by
another process.

If a security issue is discovered, contact the repository maintainer privately
through an access-controlled channel; do not publish exploit details in a
public Issue. A dedicated vulnerability contact has not been designated.
