# Asynchronous function creation dispatch

Date: 2026-11-12. Original downstream scheduling changes to `src/nmplugin`,
under its existing PolyForm Noncommercial licence. No reference code or
binaries copied. Experimental; target shader correctness, responsiveness
and FPS remain unverified.

## Isolated change

The completion-handler variants of `newFunctionWithName:constantValues:` and
`newFunctionWithDescriptor:` previously called their synchronous implementation
and completion handler on the calling thread. They now queue that same
implementation on the existing pipeline compile NSOperationQueue. The plugin
is built from `NVMTLDevice.m` as one translation unit; its existing static queue
definition precedes the import of `NVMTLObjects.m`. No additional pool is created.

Before submission, names and `MTLFunctionConstantValues` are copied. Native
function descriptors use their copy implementation, preserving descriptor
subclasses, options and specialized names; their constant-values object is
also explicitly copied. This protects queued work from later replacement/reset
of the tested values. Copying is done before the API returns and itself has a
cost. It does not authorize mutation concurrent with copying or promise a deep
copy of arbitrary nested objects/foreign descriptor implementations.

The existing synchronous `id` descriptor entry point accepts invalid objects and
returns errors. Non-copyable objects are retained and passed through to that
path; the wrapper does not introduce an unconditional `copy` exception for them.
Valid native descriptors get snapshots. Invalid named-function inputs are
passed to the same synchronous implementation. Exceptions from copying or
queued work are not converted into a new NSError contract.

Both results and errors (including a warning accompanying a result) reach the
handler unchanged. Callbacks dispatch to the user-initiated global queue,
outside compile operation slots, allowing a callback to enqueue and wait for a
nested request at width one. ARC retains queued inputs, handler, library owner
and callback results. A nil handler still returns immediately without copying
or compiling, as these two APIs did before this change. Callbacks can race API
return; this is asynchronous dispatch, not a strict return-before-callback
wall-clock guarantee.

## Resource limits and rollback

The existing width policy is unchanged: automatic 1–8, or the existing
`NVMTL_PIPELINE_THREADS` override 1–64, selected once per process. Restart the
application when changing it. It bounds active operations shared with the
ordinary async pipeline and source/stitching library APIs, not pending count,
snapshot bytes, direct synchronous calls, backend-internal threads or total RSS.
There is no new drop policy, caller-runs fallback, cache or shader transformation.
Synchronous function methods and the mesh-pipeline wrapper remain unchanged.

Rollback is a normal reviewed revert of this isolated change. No deployment,
EFI, NVRAM, BIOS, disk or OS-security changes are performed.

## Validation and acceptance

`tools/test_async_function.py` extracts both actual async method bodies and the
three existing queue/width helpers, checking the one-translation-unit import
order. It hashes input and extracted bytes, and rejects missing/duplicate
targets or missing snapshot/queue/callback behavior.

On macOS, the fixture uses real Foundation, `MTLFunctionConstantValues`,
`MTLFunctionDescriptor` and `MTLIntersectionFunctionDescriptor`. It substitutes
synchronous function creation and logging, without creating a Metal device or
executing translation. Tests cover suspended/gated compilation, mutable names,
indexed/named constant modification/reset, descriptor replacement/options/specialized names,
subclass preservation, nil/invalid inputs, nil-handler no-work behavior,
success/failure/warning propagation, callbacks outside the pool, nested waits,
owner retention/release, and 1600 mixed requests from 16 callers at each of
widths one and two. ASan/UBSan and TSan run separately.

Windows/Linux verify extraction and unsupported-native-execution refusal only.
Initial focused run `43143909880` passed the Ubuntu host checks but rejected
the fixture's subclass factory return type under `-Werror`. The fixture now
constructs the native subclass directly with `new`; warning checks remain
enabled. Corrected focused run `43144322860` passed both sanitizer variants at
widths one and two, existing async library/translation/cache regressions, both
kext builds and actual Metal plugin build/sign verification. Committed-source
and extracted-body hashes and actual host details are recorded in
`validation/async-function-20261112.md` and its JSON companion.
Target acceptance still requires real function/shader output, caller latency,
memory and frame-time A/B. Host scheduling tests cannot establish stable FPS.
