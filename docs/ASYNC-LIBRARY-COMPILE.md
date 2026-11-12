# Asynchronous library API dispatch

Date: 2026-11-12. Original downstream scheduling changes to `src/nmplugin`,
under its existing PolyForm Noncommercial licence. No reference source or
binaries are copied. This is an experimental caller-blocking fix; target
latency, shader correctness and FPS remain unverified.

## Isolated change

The completion-handler variants of `newLibraryWithSource:options:` and
`newLibraryWithStitchedDescriptor:` previously ran synchronous creation on
the calling thread. The source API only dispatched the eventual callback;
the stitching API also invoked its callback inline.

Both now snapshot their inputs and submit creation to the **existing pipeline
compile NSOperationQueue**. Source strings, compile options and stitching
descriptors use their native `copy` semantics before returning. This does not
promise an independent deep copy of every object reachable from a descriptor;
callers must not concurrently mutate nested objects used by compilation.

The synchronous methods and their translator/Apple-library bridging paths are
unchanged. Completion handlers run on the user-initiated global dispatch queue,
outside the compile operation. This allows a handler to request another build
and wait for that completion even when the compile pool has width one. Error
and warning handling retain the original behavior: source passes its NSError
alongside its result; stitching clears the error for a successful result.
A nil handler still submits creation, as before. Result/error/handler/owner
lifetimes are retained by ARC blocks. Exceptions are not converted into a new
NSError contract by this change.

Asynchronous callbacks can race the API's return; the guarantee tested here is
that compilation is queued and callbacks do not execute inline on the caller
or occupy the compile operation, not a wall-clock ordering promise.

## Resource scope and rollback

There is no additional worker pool. These two APIs share the concurrency budget
already used by asynchronous ordinary pipeline creation. Existing automatic
width selection is unchanged (1–8); the existing `NVMTL_PIPELINE_THREADS`
override permits 1–64 and is read when the queue is first initialized. Restart
the application for an isolated width change. Width one serializes builds while
still returning from these asynchronous APIs without doing the build inline.

The width limits **active queued compile operations**, not all compiler threads,
direct synchronous calls, backend-internal work or total process memory. Pending
operations and their snapshots are not given a new count/byte limit. There is no
drop, caller-runs saturation fallback, new caching, prewarming or shader change.
Async function creation and mesh-pipeline wrappers are outside this change.

Rollback is a normal reviewed revert of this isolated commit. No install, EFI,
NVRAM, BIOS or OS-security changes are performed.

## Validation

`tools/test_async_library.py` extracts the two actual method bodies and the three
existing compile-queue/width helper bodies. It rejects absent/duplicate targets,
uses real Foundation and Metal descriptor classes on macOS, and substitutes only
the synchronous compiler and logging. No Metal device or shader compiler is run.

The native fixture tests widths **one and two**, suspended-pool input snapshots,
API return while synthetic compilation is gated, shared active concurrency,
success/failure/warning propagation, nil inputs/handlers, callback reentry and
owner retention/release. At each width it submits **1600 requests from 16 callers**
and checks output identity and exactly-once completion. Separate ASan/UBSan and
ThreadSanitizer runs are required. Reports hash committed input and extracted
method/helper bytes. Windows/Linux tests only verify extraction and refusal of
unsupported native execution.

Focused run `43142206872` passed both sanitizers at widths one and two, the
existing translation/cache regression checks, both kext builds and the actual
Metal plugin build/sign checks. Source hashes and host details are recorded in
`validation/async-library-20261112.md` and its JSON companion.
Real source/stitching compilation,
target output, launch time, memory and frame-time A/B remain separate acceptance
work; a synthetic gated build returning early is not a measured speedup.
