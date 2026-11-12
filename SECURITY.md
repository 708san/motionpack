# Security guidance

MotionPack is experimental pre-alpha software. Do not use its current tools to
open untrusted packages in a production or high-privilege environment.

## Dependency inventory

The offline generated inventory at [docs/DEPENDENCY_INVENTORY.json](docs/DEPENDENCY_INVENTORY.json) covers hash-pinned Python requirements, npm lock entries, full-SHA GitHub Actions and digest-pinned workflow images. Regenerate and check it with 'python3 tools/dependency_inventory.py' and 'python3 tools/dependency_inventory.py --check'. It is a scoped provenance/drift record, not a complete software bill of materials (SBOM): bundled Action, OCI image, hosted runner and native wheel dependencies are not enumerated. The image license composition remains unassessed. License metadata is evidence for review, not a legal determination; MotionPack itself remains unlicensed.

The bounded reader in `tools/archive_reader.py` supports experimental v0.1/v0.2/v0.3/v0.4
packages. It checks ZIP member names and metadata, enforces configurable size
and compression-ratio limits, and reads only the manifest and referenced image
assets. It does not extract arbitrary ZIP members. Optional `source/` entries
are not decompressed, inspected for secrets, or returned by the reader.
The default reader limits are 40 MiB per archive, 1,024 entries, 2 MiB for the
central directory, 1 MiB for the manifest, 12 MiB per asset, 32 MiB total
referenced assets, 40 MiB total declared expansion, and a 100:1 compression
ratio. These are configurable tool defaults, not format-wide limits. ZIP64 and
multi-disk archives are rejected.

For each non-directory entry outside `source/`, the reader inspects at most 512 decompressed bytes for common ZIP, gzip, bzip2, xz, 7-Zip, RAR, and tar headers. Recognized nested archives are rejected even when unreferenced or renamed. This is bounded signature detection, not general file-format identification; uncommon variants and polyglot files may not be recognized. `source/` remains opaque and is not decompressed or inspected.

Before opening an archive path, the reader checks that it resolves to a regular
file and captures its `(st_dev, st_ino)` identity. After open, it verifies that
the descriptor is regular and has the same identity before parsing or copying.
A substituted file object is rejected when the reported identities differ.
If Python reports an unavailable or invalid identity tuple (including a missing
or non-integer device/inode value, or a nonpositive inode), the reader fails
closed before open. The reader cannot guarantee that every positive
`(st_dev, st_ino)` is unique or stable; filesystem ID reuse or collisions can
make a substitution undetectable. A
symlink to a regular file remains supported when both checks resolve to the
same target. This comparison is not an atomic open and does not eliminate all
path races or protect against concurrent writes to the same opened file.

The reader uses `O_NONBLOCK` where the operating system exposes it (Unix in
Python). On a platform without that flag, a substituted blocking special file
may block before the descriptor check can reject it. Windows CI exercises the
identity check on its hosted filesystem; this does not guarantee behavior for
every Windows filesystem or every reparse-point race. The reader does not
guarantee safe handling of all paths another process can change concurrently.

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
for arbitrary renderers. The generated preview still uses browser-native
image decoding; the optional host API `decode_raster_assets_isolated()` runs
Pillow in a separate worker with documented resource limits, but the worker is
not a sandbox. Bounded Atheris coverage-guided targets exercise the ZIP reader,
SVG validator and raster header parsers. A separate black-box mutation target
exercises the isolated decoder; Atheris does not receive coverage feedback from
Pillow or its native codecs.
All targets use a 15-second pull-request run and a 300-second weekly/manual
campaign. Inputs are capped at 64 KiB, each case has a 2-second timeout, and
the shared job has a 25-minute limit so four scheduled campaigns can complete
with setup overhead. This remains bounded fuzzing, not continuous fuzzing.
The default `read_package()` path uses the isolated wrapper's platform-specific
process and memory controls; it is defense in depth, not a sandbox. The explicit
`read_package_in_process()` path parses in the caller process and should be used
only when that behavior is intentional. Keep packages and their assets untrusted.

## Default isolated archive reader

`tools/isolated_archive_reader.py` provides `read_package_isolated()`, which
backs the default `read_package()` API. Callers may also invoke it directly to
customize timeout or memory settings. The previous direct parser remains
available as `read_package_in_process()`; it runs in the caller process without
a worker deadline or process-level memory cap. The isolated wrapper creates a
private temporary directory and starts a fresh
Python worker without a shell. The worker snapshots at most 40 MiB of a regular
input file there while hashing the copied bytes, then makes a second bounded
read of the same open file and requires the byte count and SHA-256 digest to
match. This detects content changes that leave size, identity, and modification
time unchanged, at the cost of reading up to another 40 MiB. It is not an
atomic filesystem snapshot or a lock against concurrent writers. The parent enforces the deadline
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
- Windows applies both a 512 MiB per-process committed-memory limit and a
  512 MiB job-wide committed-memory limit using a Job Object before sending
  the worker its request. The job-wide limit covers the worker and processes
  assigned to that job.
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

## Opt-in isolated raster decoder

`tools/isolated_raster_decoder.py` exposes `decode_raster_assets_isolated()` for
host runtimes that already hold validated, manifest-referenced asset bytes. It
starts a new Python worker and passes bounded bytes over standard input; the
worker never opens package-controlled paths. Only static PNG, JPEG and WebP are
accepted in this increment. Animated WebP, SVG and other formats are rejected.
The default offline preview remains on the browser image-decoding path. The packager also offers the explicit `--isolated-raster-decode` option: every referenced runtime asset must be a static PNG, JPEG or WebP; SVG, animated WebP and unsupported formats are rejected. The existing worker decodes validated asset bytes one at a time under the shared 64-megapixel budget, and the packager embeds only canonical PNG bytes in the HTML preview. The aggregate 64 MiB encoded PNG budget counts every asset-ID data URL, including repeated references to the same path, to bound preview expansion. The `.motionpack` archive keeps the original asset bytes and manifest unchanged. Raster decoding uses a shared 300-second package-wide deadline and a 30-second maximum deadline for each worker call. Decode, timeout, worker and response-validation errors fail before the output directory or either output file is created or replaced. This is process isolation with resource controls, not an OS permission sandbox; macOS has no hard whole-process memory cap. The default packaging path does not import or require Pillow at runtime unless the option is used.

The adapter returns straight RGBA pixel buffers and applies the existing tool
ceilings: 8,192 pixels per edge, 16 million pixels per asset, 64 million header
pixels total, 64 million decoded pixels total, 12 MiB per asset and 32 MiB of
input bytes. A wall-clock deadline defaults to 30 seconds and may be set up to
300 seconds. Responses are capped and checked for expected asset IDs, format,
dimensions and exact RGBA byte lengths. A timeout, malformed response, worker
failure or limit rejection discards the entire result. There is no implicit
fallback to browser decoding. Pillow is optional and pinned in
`requirements-image.txt`; install it explicitly with hash verification and
binary wheels only (the lock covers the Linux x86-64, macOS arm64 and Windows
x86-64 Python 3.12 CI targets):

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements-image.txt
python -m unittest discover -s tests -p test_isolated_raster_decoder.py -v
```

The worker uses a 512 MiB address-space ceiling on Linux and a 512 MiB Job
Object committed-memory limit on Windows. The Windows Job Object is assigned
after process creation but before any asset bytes are sent, so Python startup
is outside that memory limit. macOS has no hard whole-process memory cap here.
Process separation and these resource controls do not reduce
the worker's OS file or network permissions; this adapter is not a sandbox or a
production-safe import guarantee. Pillow's bundled native codecs remain part
of the attack surface and require version/security updates.

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

The isolated raster decoder target is `tests/fuzz_raster_decoder.py`. It invokes
`decode_raster_assets_isolated()` with reviewed malformed PNG/JPEG/WebP seeds
and generates small valid PNG/JPEG/WebP seeds through the already pinned Pillow
dependency. Ordinary image rejection is expected; worker crashes, malformed
worker responses, and timeouts fail the target. The target keeps dimensions at
512 px per edge, total pixels at 262,144, each input at 64 KiB, and the corpus
at 16 files / 1 MiB. It uses the same 15-second PR and 300-second weekly/manual
budgets, 2-second case timeout, and 1,024 MiB job RSS limit. The decoder target
is black-box with respect to Pillow: Atheris does not receive coverage feedback
from the child worker or its native codecs. It mutates inputs and checks bounded
results, worker failures, resource-limit failures and timeouts, but it is not
coverage-guided inside Pillow. Process isolation does not sandbox the worker or
prove decoder safety.

Atheris is test-only and does not enter the runtime package. Version 3.1.0 is
pinned to the Linux CPython 3.12 wheel hash; the upstream project is Apache-2.0.
Pillow is also installed from the existing hash-locked `requirements-image.txt`
with binary wheels only. PyPI lists no provenance attestation for Atheris 3.1.0,
so the workflow uses hash-locked wheels in an isolated environment, with
read-only repository permissions and no secrets. Review generated crash inputs
before adding them as regression fixtures; the workflow does not upload or
commit fuzz outputs.

The project packager emits only `manifest.json` and its referenced runtime
assets; it does not automatically add unreferenced project files or `source/`.
The validator rejects runtime references into `source/` and local project paths
with symlink components. The packager snapshots the bounded asset bytes used by
validation and uses those same bytes for the ZIP and preview. It scans raw
serialized manifest (including asset paths) and referenced-asset bytes for a
small set of private-key headers and GitHub, Slack, OpenAI, and AWS credential-like
patterns, then prints only a generic metadata location or the 1-based
referenced-asset ordinal and category to standard error. It does not print
paths or matched values. By default, this is warning-only and matching
content remains in the ZIP and preview. Pass `--fail-on-secret-like` to reject
a match before creating or replacing either output. The opt-in mode can reject
legitimate assets that match a heuristic. Scanning can miss transformed or
pixel-encoded secrets and can produce false positives; maintainers must review
assets before distribution. Recognized secret-like patterns are also redacted
from packager validation errors when an invalid asset path contains a match.

On platforms that support directory-relative no-follow opens, each project
path component is opened beneath a pinned directory. Other platforms recheck
path components and file identity, but cannot fully rule out every concurrent
directory replacement. Build from a project tree that is not being changed by
another process.

If a security issue is discovered, contact the repository maintainer privately
through an access-controlled channel; do not publish exploit details in a
public Issue. A dedicated vulnerability contact has not been designated.
