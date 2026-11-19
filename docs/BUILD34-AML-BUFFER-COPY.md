# Build34 AML log-buffer copy candidate

The residual GUI stutter now has a specific AML hot method to evaluate. A fresh
finite native observation found 395 of 406 query on-CPU samples in the firmware
log-buffer `MOVE` method. A narrow local batch-copy candidate passes offline
AML equivalence checks, but is **not installed or hardware-accepted**. The active
build34 VBL candidate and the accepted owner baseline remain distinct.

This follows the [direct HIGH queue-delay measurement](BUILD34-VBL-SCHEDULING.md#pending-to-dispatch-delay-measured-directly).
That earlier trace measured 105 callbacks queued for more than 80 ms, including
Mach timers delayed 132–202 ms. The new trace answers which AML method consumes
runnable query work; it does not repeat a timer/FPS benchmark or establish that
all GUI pauses have one cause.

## Native method observation

The observation ran on November 19, 2026, on macOS 26.7.2 build 25G332, in the
same boot with VBL source `439f8a5bc3e086770df7b576897fbb11d7ccc9f1` active.
Matching KDK image identity was verified against the loaded ACPI platform image.
The address of the interpreter's current-walk state was calibrated from an
actual live RIP-relative instruction. Every recorded method sample also checks
the interpreter's owning thread against the current thread, the thread/walk/
namespace descriptors and the method type. No Apple object was modified.

| Twelve-second query observation | Result |
| --- | ---: |
| Query entries / exits | 18 / 17 |
| Complete `_Q47` / `_Q48` calls | 9 / 8 |
| Query on-CPU method samples | 406 |
| Samples passing all identity/type guards | 406 |
| `MOVE` samples, `_Q47` / `_Q48` | 50 / 345 |
| `MOVE` share of query samples | 97.291% |
| Probe errors / reported drops | 0 / 0 |

Other sampled methods were `MBGS` (6), `NEUP` (2), `UP_L` (2) and `DB2H` (1).
All 406 samples belong to complete queries. One further `_Q48` was still open
at the finite cutoff and had no method samples; this is right-censoring, not a
failed or terminated firmware operation. Each of 16 CPUs recorded 1,185 profile
ticks. Samples estimate where executing query work occurs; they are not exact
CPU-time or wall-time measurements and do not observe acknowledgment values.

Two preliminary traces produced no usable method samples and are excluded from
method attribution. The final profile uses the previously verified current-
thread query map. Allocator-specific no-hit probes and a thread-local profile
predicate must not be interpreted as evidence that interpreter work was absent.
All observations exited normally with empty stderr, unchanged ACPI debug flags
and the existing ktrace session preserved.

## Why the log buffer is a useful target

Private review of the byte-matched original firmware resolves a 4,096-byte
log buffer. When full, its existing caller opens 16 bytes of space by invoking
a serialized byte-by-byte move of the other 4,080 bytes, then clearing the tail.
Both observed EC queries reach this logging path. Across the original table set,
the method name occurs at one declaration and one call site.

This explains a mechanism that can become much more expensive after the first
buffer fill, and is consistent with the initially-smooth-then-sluggish report.
The first fill time was not captured. Neither this mechanism nor the sample
concentration substitutes for a controlled hardware treatment. The earlier
sleep-compensation finding still stands: firmware sleep releases group capacity;
the new target is repeated interpreted copying during runnable execution.

Do not disable either query, delete logging, shorten polling, force an
acknowledgment or bypass the power-limit updates. Those are unnecessary for the
candidate below, and the acknowledgment contract remains unverified.

## Exact local candidate and rollback

The private candidate replaces only the known 16-byte shift of a 4,096-byte
buffer with bounded AML buffer operations. It first captures the retained bytes
and original tail into temporary buffers, then writes their concatenation back
to the existing buffer and updates its index. The original caller still clears
the tail. Keeping the existing buffer object matters for aliases, fields and
outstanding index references. All other argument or buffer-size cases delegate
to the unchanged original method.

An exact declaration-only rename retains that original implementation under a
fallback name; the existing call site keeps its original name. The wrapper
remains serialized. The private table preview changes one name byte and its
checksum, with zero original method-body or call-site bytes changed. A whole-
table hash guard rejects drift; the proposed OpenCore match also restricts the
table signature, length and OEM table ID and must match once. This is a local
preview, not a generic patch for other firmware.

The configuration preview preserves all existing Add/Patch entries and all
other configuration sections. Its only existing-file change is `OC/config.plist`,
with one new `SSDT-BFCOPY.aml` table: 357 original files become 358 preview files.
Official OpenCore 1.0.8 `ocvalidate` reports no issues. Neither file was written
to the real EFI, no startup job was staged and no power action was scheduled.

Rollback retains the exact original configuration and full original manifest.
For a future authorized trial, restore that exact configuration and remove only
the byte-matched candidate table. A subsequent ordinary boot restores the
original name/implementation. Driver images and the running VBL candidate are
outside this ACPI change; do not unload the desktop driver, kill WindowServer,
reinstall the rejected S5 candidate or replay any consumed hardware scope.

## Offline execution evidence

An ACPICA `R09_25_20` / `20200925` simulator was built privately from commit
`70add34a9a4729b5496d0695ad14d6a1dc435879` after reviewing the component's
license headers. It executes only mock tables without OperationRegions. No real
machine firmware was executed in the simulator, and no third-party source,
binary, firmware excerpt, KDK material or personal configuration is published.
The existing pinned private iasl compiled the candidate without errors/warnings.

| Offline validation | Passed |
| --- | ---: |
| Single shift and full scroll equivalence cases | 22 |
| Four-successive-scroll comparisons | 2 |
| Unexpected buffer-length fallback comparisons | 4 |
| Total actual-AML equivalence cases | 28 |
| Strict/slack implicit-return compatibility modes | 2 |
| Exact-table preview/refusal cases | 13 |

The ordinary cases compare all buffer bytes, index, size, type, alias, an
existing buffer field and an existing index reference. Three distinct byte
patterns, zero and boundary shifts, the unchanged caller's tail clearing and
non-target inputs are included. Repeated-scroll and unusual-length cases compare
complete buffers, indexes and lengths. The guard cases reject unknown or changed
tables, malformed/truncated data, changed flags/length, ambiguous declarations,
existing fallback names and invalid checksums.

An initial simulator fixture's interpreted pattern-generation loop timed out;
it is excluded and was replaced with static input buffers. An early candidate's
slack-mode implicit return differed from the original; that difference was
corrected before all final checks. The final candidate returns no object in
strict mode and the original implicit zero in slack mode. These are simulator
semantics checks, not proof of current Apple interpreter behavior under load,
allocation-failure behavior, live concurrency, GUI latency or FPS.

## Related upstream leads

A fresh read of Apple's published XNU HEAD still resolves to
`f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`. Its downloaded `thread_call.c`
hash matches the previously reviewed snapshot; no newer supported reassignment
setting for an existing callback was found in that review. ECEnabler at
`29dcde79b51a082ab9816184eb5ccdf3c5115a97` adapts EC field access widths;
it is not a query-queue or this Memory-buffer copy fix. No ECEnabler code was
adopted. The [upstream input-lag discussion](https://github.com/luuumi-dev/nullarc/issues/13)
contains USB/MSI community workarounds, without demonstrating a repair of this
machine's independently measured system-timer backlog. No such EFI change was
made here.

## Current state and next admission

Final independent readback passed the active VBL image/cache, full metadata and
all 416 records/29 codeless entries with 415 unrelated images preserved, exact
accepted recovery, original loaded ACPI/full EFI recovery and current-boot
accelerated startup. The same WindowServer survived without new errors or
matching reports. Acceleration, desktop takeover and the daily PR28 setting
remain enabled; its 250 ms budget and WindowServer exclusion are unchanged.
Resident monitors remain disabled. The accepted owner baseline remains
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496`.

The next stage is a separately reviewed and authorized ACPI trial with a fresh
scope compatible with the currently active VBL image. It needs an exact original
control, candidate-only ACPI/EFI expectations, unchanged startup/admission limits,
independent loaded-table/body verification and exact recovery before a bounded
normal-priority GUI/timer comparison. Old startup/GUI/GPU receipts must not be
replayed. No general stutter repair, physical FPS or long-term stability is
accepted yet. See the [sanitized record](validation/build34-aml-buffer-copy-20261119.json).
