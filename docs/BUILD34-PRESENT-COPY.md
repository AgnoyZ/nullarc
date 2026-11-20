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

## Isolated packed-stride candidate

`performTransaction` copies every row separately. Its inline SSE path saves
and restores ten XMM registers for every row. A candidate can combine rows
only when SSE is enabled, source/destination are aligned, both strides equal
the copied row length, and that length is a nonzero multiple of 64 bytes.
The source candidate implements just this selection and keeps the existing
row/tail path otherwise. It preserves l10r narrowing, surface readiness and
mapping ownership, the final store fence and transaction completion. A
2560-by-1600 packed frame can save/restore XMM state once rather than once
per row; that reduction is a code-path property, not a measured FPS gain.

[The production-code fixture](../tests/test_build34_present_copy.py) extracts
the actual copy block and SSE assembly. All 2,086 ASan/UBSan cases pass full
byte comparison against a scalar reference, including both formats, source
immutability, entire guard/padding regions, zero/short/full-size frames,
unequal pitches, alignment, scalar/SSE controls, tails and same-address copy.
The default suite, 25 complete-cache methods and 60 unchanged VBL CPU
assertions pass. One VBL test initially could not overwrite an older
root-owned ignored test binary; running that same CPU fixture with the
necessary file permissions passed. This was not a production/compiler or
hardware failure.

[The offline native recipe](../tools/build34_present_copy.py) freezes every
accepted accelerator source and licence input at `439f8a5`, requires the
exact complete old/new copy-source hashes, and uses audited MacKernelSDK
`3f750085caa17ec3a7880f11c11bf4f48cd6a164`. The unchanged baseline build
reproduces the installed executable exactly. The signed x86_64 candidate
passes architecture/signature checks with the same imports. Source, recipe
and frozen SDK readback pass. No kernel, plugin or native ABI change is made.

A fresh finite offline-cache scope links through the normal approved bundle
paths, with the same explicit-only bundle set and no authentication bypass.
A separately bounded guard protects the temporary executable staging. The
accepted disk executable was restored and its signature checked before the
guard ended; the installed auxiliary cache and startup jobs never changed.
The candidate cache's complete 416/29 metadata comparison admits only the
PhxAccel image change. All matching policy, paths, dependencies and
boot/system-collection links remain exact. Separate independent readback
reparsed this metadata, checked candidate/source signatures and the full
retained runtime/EFI/cache/AML/jobs, and observed desktop progress, zero
checked errors and no new report. No cache worker, guard, panel, trace,
native probe or power process remains. See
[offline evidence](validation/build34-r2-packed-copy-offline-20261120.json).

**This candidate is not installed or loaded.** A fresh R2a-compatible
controller must retain the current accepted R1b/VBL/AML/plugin as exact
recovery and preserve the 45/150/300-second startup bounds, daily PR28
250 ms/WindowServer exclusion and monitor-off policy. Do not use an old
controller that would roll the kernel, VBL or AML back further. A separate
new-boot loaded-image check and controlled display comparison remain required
before R2a hardware acceptance or R3.

The [separate R2a adapter](../tools/build34_present_copy_host.py) provides that
source/preparation path without changing historical hosts. Its distinct
sealed scope validates the exact two-image delta, retained EFI/kernel/AML
manifest and baseline jobs. Its final contract overlay changes only the
accelerator/cache hashes and accelerator image identity. Preparation uses
the still-loaded accepted accelerator identity for live checks while disk
and signature checks continue to require the candidate. Recovery checks
all inputs before the first mutation, restores only the accelerator/cache
pair and current retained jobs, and leaves EFI/kernel/plugin/AML untouched.
It verifies disk restoration without requiring the failed accelerator to
have started or treating a new diagnostic report as a failed disk restore.

Nine CPU fixture methods cover exact/unknown deltas, immutable derivation,
preserved kernel/ABI/EFI, daily configuration and current job accounting,
pre-restart identity separation, refusal before writes and two-image-only
recovery. The inherited bounded startup, finite watcher and no-daily-power
policy remain. This adapter is source-tested only; no new live scope,
candidate deployment or ordinary restart has occurred at this checkpoint.

The first inactive preparation then refused before any live image/job write:
the historical protected map gives `phxboot-off` an empty-file hash, while the
accepted accelerated installation intentionally has that disabling marker
absent. The new adapter originally tried to hash it as a required file. The
correction requires exact absence for that single historical switch and the
known empty-file hash; all other missing protected files and symlinks remain
refused. It does not create the marker or loosen a driver/image gate. Two
additional CPU methods cover that distinction. Keep the rejected private
packet and use a fresh scope after this source fix.

This does not implement AMD asynchronous presentation or a DCN flip. Moving
the wait/copy to a worker still requires bounded ownership, cancellation,
stop/sleep handling and correct completion; removing the wait or NVIDIA vendor
check is not a safe optimization. R2 optimization acceptance and R3–R6 remain
pending. No FPS or long-term stability improvement has been demonstrated.
