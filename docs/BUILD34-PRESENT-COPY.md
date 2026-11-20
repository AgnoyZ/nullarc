# Build34 R2 display wait and CPU scanout copy

## Accepted baseline measurement, November 20

[R1b's bounded pressure proof](BUILD34-RING-BACKPRESSURE.md) passed before
this R2 work began. The same accepted R1b/VBL/optimized-AML/accepted-plugin
installation remains active on macOS 26.7.2 build 25G332. No driver, startup
job, configuration, cache, EFI, ACPI or power change was made by profiling.
PR28 remains enabled at 250 ms with WindowServer excluded; resident monitors
remain disabled.

The finite [trace recipe and strict parser](../tools/build34_present_profile.py)
observe only PhxAccel's display transaction and its nested surface-wait and
copy-preparation methods. The admitted image is the existing
`a206d983fca62dd7959cc701fb9f95d5490da78986aac02dbb67ed00410325e7`
executable. Disassembly verified a single final `popq %rbp; retq` epilogue
per method. This host's FBT return offsets point to that final pop at
`0x7ac`, `0x162` and `0x405` respectively. These are actual method exits,
not a tail call to a still-running helper. The parser refuses other offsets,
failed/overlapping/unpaired transactions, diagnostics and empty samples.

The [12-second AppKit stimulus](../tools/anim/present_profile.m) is a small
CPU-drawn nonactivating panel, launched through Launch Services in the
console session. It ignores mouse input and closes automatically. Its source
does not explicitly create a Metal device; framework/compositor GPU use is
not excluded. All 23 onscreen checks passed, with 712 draw callbacks and
713 timer callbacks. The panel and its launcher exited normally. These
callback counts are not physical refresh or game FPS.

The eight-second trace contains 378 entries and 378 complete transactions,
all in kernel context, with no partial transaction at either boundary.

| Traced stage | Median | P95 | Maximum |
|---|---:|---:|---:|
| Entire display transaction | 3.457 ms | 5.932 ms | 9.522 ms |
| Nested GPU surface wait | 0.123 ms | 1.295 ms | 3.122 ms |
| Copy-readiness preparation | 0.004 ms | 0.009 ms | 0.049 ms |
| Remaining transaction work, including copy | 3.285 ms | 5.231 ms | 9.371 ms |

The residual is not an isolated copy timer and includes other work and trace
overhead. Do not add percentiles/maxima from different rows into a frame time.
The wider counter interval surrounds trace setup and the complete panel run:
667 successful surface-sourced transactions, zero flips, and 1,600,731 added
copy microseconds give a mean of about 2,399.90 us per copy in that interval.
That mean is not a distribution for the eight-second traced sample. This is
a bounded baseline observation, not a controlled FPS comparison.

The separate independent reader replayed the frozen trace parser and checked
the same boot, exact loaded/mapped images, full 358-file EFI, complete 416/29
cache metadata, loaded AML, startup receipts and exact recovery/jobs. The
same WindowServer survived, VBL/copy counters advanced, four checked errors
remained zero and no matching diagnostic report appeared. SSE and vsync were
both one before and after. No panel, trace, probe or pending power process
remains. See [sanitized evidence](validation/build34-r2-present-baseline-20261120.json).

## Preserved measurement refusals

The first idle trace ended cleanly but saw no new transaction. A panel trial
then produced 720 draws and passed 24 onscreen checks, but its first exit
implementation hid/closed the window without ending the app's run loop.
The completed hidden panel was identified by its exact executable/arguments
and terminated; this trial is not accepted. Its WindowServer-PID filter also
missed the actual kernel-context transactions.

A fresh panel with normal application termination captured 376 complete
transactions under the exact-module filter and exited. The first parser
expected `retq` offsets, but FBT reported the preceding final pop, so it
correctly refused its configured endpoints. Disassembly confirmed all three
actual epilogues before updating the parser. The final fresh trial above
passed the complete measurement and independent reader. Preserve all earlier
refusals; do not relabel them successful or replay their scopes.

Six CPU parser/program methods cover complete/boundary samples, empty runs,
unknown endpoints, failures, overlaps, diagnostics and finite module scope.
The default suite also exposed a pre-existing CPU trace-double scheduling
race: its short post-READY sleep could expire before the parent ran. That
success fixture now exits after an explicit fake-probe `G` acknowledgement;
production readiness/retirement limits and all refusal tests are unchanged.

## Next isolated candidate

`performTransaction` copies every row separately. Its inline SSE path saves
and restores ten XMM registers for every row. A candidate can combine rows
only when SSE is enabled, source/destination are aligned, both strides equal
the copied row length, and that length is a nonzero multiple of 64 bytes.
Otherwise keep the existing row/tail path. Preserve l10r narrowing, surface
readiness/mapping ownership, the final store fence and transaction completion.
First compare actual extracted production code against full-byte reference
images, including padding/guards and all fallback paths. Native build/cache
admission and a separate real loaded-image comparison are still required.

This does not implement AMD asynchronous presentation or a DCN flip. Moving
the wait/copy to a worker still requires bounded ownership, cancellation,
stop/sleep handling and correct completion; removing the wait or NVIDIA vendor
check is not a safe optimization. R2 optimization acceptance and R3–R6 remain
pending. No FPS or long-term stability improvement has been demonstrated.
