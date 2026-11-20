# Build34 R3 exact completion and safe retirement

Current November 20 checkpoint: R1a/R1b and R2a's bounded functional trial
have passed. R2a's installed combination remains active; no speedup is
established. R3 has a tested **source-only Mesa bookkeeping prerequisite**,
not an installed exact-wait implementation. R4–R6 have not started.

## Why a kernel-only change is unsafe

The production build34 `gpuRetired()` is a conservative contiguous watermark
across the compute and GFX queues. Its consumers include `vmBind`,
`vmidFree`, QueryInfo, native wait results and CPU fence publication. A later
completed GFX fence cannot safely advance that global watermark past an
unfinished earlier compute submission. Keep these reclamation semantics.

There is a second, user-space contract to preserve. The pinned MIT Mesa
`ac_darwin_sync.c` calls `note_retired(s, seq)` after any successful nonbusy
backend wait, in addition to consuming the returned watermark. `fold()` then
marks **every** attached sequence at or below that value complete. Merely
changing the kernel's busy result to exact-target completion would therefore
falsely signal an unrelated lower-sequence syncobj, even if the kernel still
returned a conservative watermark in output slot 1.

The new [actual-source CPU fixture](../tests/test_build34_exact_completion.c)
demonstrates this transition hazard on the unchanged pinned provider: the
fake backend reports global watermark 9, exact sequence 20 complete and
sequence 10 pending. Waiting for 20 makes the old provider falsely report
10 complete. **This models a proposed exact backend; it is not evidence
that the installed conservative backend returned such a response.**

## Isolated prerequisite

[Patch 0003](../mesa-patches-build34/0003-radv-exact-completion-bookkeeping.patch)
changes only `ac_darwin_sync.c`. It retains `note_retired(s, retired)` for
the backend's safe prefix, but replaces the second prefix promotion with
`note_completed(s, seq)`. Under the provider mutex this folds only current
binary/timeline references to that exact sequence. A signaled timeline point
still implies lower points on that same timeline, as before. Unrelated
objects are not signaled. Cloned providers continue to share the same state.

The callback runs without the mutex, so completion must look up current
payload references after reacquiring it. Reset/destroy/handle reuse during
the callback must not signal a replacement sequence. No permanent set of
completed sequence numbers, new allocator or extra resource lifetime is
introduced. Late references can ask the backend again. Backend errors and
the legacy conservative-prefix response keep their existing behavior.
The exact-reference scan runs only when the completed target is above the
returned safe prefix; legacy prefix-covered completions incur no new scan.

The [offline runner](../tools/test_build34_exact_completion.py) requires all
30 source/dependency hashes in the existing reviewed Mesa manifest. It
freezes separate baseline/candidate closures, initializes a private source
repository for unambiguous patch application, requires exactly one changed
file and preserves the original MIT notice. It verifies inputs and all
tracked driver/plugin/native-ABI/phxctl bytes again afterwards. The old
original34 artifact admission tools are untouched.

Run with an explicitly selected matching source and a fresh ignored output:

```sh
nice -n 15 make test-build34-exact-completion \
  MESA_SOURCE="$MESA_SOURCE" \
  EXACT_COMPLETION_OUT=build/build34-r3-exact-bookkeeping-new-private
```

On November 20 both actual-source executables compiled under ASan/UBSan.
The unchanged baseline reproduced the counterexample. The candidate passed
**4,741 checks**, including 128 distinct sequence gaps, late attachment,
binary reset/signal, independent timelines, shared clones, transfers, safe
global-prefix folding even on busy replies, device-loss/error propagation,
and deterministic reset/destroy/reuse races while the callback is blocked.
The default `make test` suite also passed.
Linkage checks exclude IOKit, Metal and Vulkan device runtimes. No GPU code
was submitted or simulated, and no installation, load, configuration, job,
EFI/cache/ACPI or power operation occurred. See
[sanitized evidence](validation/build34-r3-bookkeeping-offline-20261120.json).

## Remaining admission work

This patch is a prerequisite, not the complete R3 optimization. Do not enable
an exact kernel/backend response yet. Before a paired native candidate:

1. Add a separately negotiated exact-target operation while keeping legacy
   waits and the safe output/global reclamation watermark compatible. Bind
   targets to actual submission ownership, queue selection/generation and
   teardown; never infer completion from a missing/reused history slot.
2. Correctly handle wait-any and query across multiple independently pending
   sequences. The current provider polls the lowest pending sequence, and
   query refreshes only the newest; global-prefix assumptions are unsuitable
   for a fully exact backend. The prerequisite above changes neither path.
3. Audit cross-queue dependencies. `acd_sync_cs_wait_ready` currently treats
   a sequence on the same connection as already ordered before a subsequent
   submission. That assumption needs an explicit queue-order/dependency
   solution before allowing independent queue completion to shorten waits.
4. Separately validate AMD completion-event/interrupt routing and lifetime,
   lost-wakeup rechecks, bounded fallback, cancellation and stop/sleep.
   Existing RELEASE_MEM packets still request no interrupt. Do not copy
   NVIDIA event selectors or set interrupt bits without a working route.
5. Require byte-exact CPU regressions, frozen native provenance, a fresh
   compatible recovery scope, exact loaded images and bounded dual-queue
   full-arena hardware evidence before R3 acceptance or advancing to R4.

Current rollback is simply to leave this source patch unapplied to the
installed runtime; there is no deployed R3 state to undo. The accepted R2a
installation, R1b kernel, optimized AML, accepted plugin, daily PR28 250 ms
with WindowServer excluded, disabled resident monitors and 45/150/300-second
startup bounds remain intact. Neither FPS nor long-term stability is claimed.
