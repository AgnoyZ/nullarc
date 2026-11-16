# Historical compute IB fetch visibility experiment

Current status on 2026-11-16: **withdrawn by the owner; build41/build42 are not candidates**.
Active investigation is restricted to [default build34](BUILD34-SCOPE.md).
The implementation, recipes and validation below are historical records, not
an active installation, compilation or testing plan.
The observed native IB wrong value is not yet declared fixed. No driver was
installed or loaded and no new GPU execution or reboot was performed during
source preparation. The default branch remains at `64f3d99` with
A1/A2/corrected-A3; wait promotion and accelerated desktop remain on HOLD.

## Build34 baseline requirement

On 2026-11-16 the owner specified that all local hardware tests and future
development use PhxBringup build34 as the baseline. The approved source
checkpoint is `upstream34/vram-layout-fix` at
`64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`, including A1/A2/corrected-A3.
Derive each isolated fix from that checkpoint without mixing unrelated
downstream wait, lifecycle, ABI or initialization changes. The owner subsequently clarified that
build41/build42 are withdrawn entirely from candidate consideration. Work must
focus exclusively on default build34; do not continue either withdrawn path.
Keep the historical identifiers and original build34 checks intact. This
clarification does not authorize installation, loading, GPU execution or reboot.

## Why this change

The [freshness comparison](NATIVE-IB-FRESHNESS-DIAGNOSTIC.md) reproduced pass 1's
`0xde` instead of `0xdf` at BO offset `0x2010` after rewriting and resubmitting
the same IB address. Its separately booted immutable fresh-slot comparison
passed both complete 16-KiB checks. The [CPU publication comparison](NATIVE-IB-PUBLICATION-DIAGNOSTIC.md)
then failed identically with and without five IB-only `CLFLUSH` instructions
and `MFENCE`. Those trials prioritize command modification/address reuse;
they do not identify CPU visibility, CP prefetch, GPU cache, shader state or
fence/data ordering as the root cause. All old scopes remain consumed.

The present kernel emits `INDIRECT_BUFFER` followed by `RELEASE_MEM`.
The probe's synchronization packet is inside the indirect buffer. This candidate
adds a compute-ring synchronization packet before the first IB. This places
the operation outside user command memory and before IB emission. It does not
prove when a GPU prefetch occurs or that the hardware honors the intended order.

The reviewed primary reference is Linux v6.12, fixed commit
`adc218676eef25575469234709c2d87185ca223a`,
`drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c`, `gfx_v11_0_emit_mem_sync`, and
`amdgpu_ib.c`'s conditional `AMDGPU_IB_FLAG_EMIT_MEM_SYNC` call.
The same reference and MIT-style license notices were audited in the
[publication record](validation/native-ib-publication-diagnostic-20261116.json).
This independently encoded eight-word packet uses those reviewed fields;
no external implementation or header is copied. Linux's conditional operation
does not establish that every submission requires it or that its absence
caused this machine's wrong value.

## Minimal source change

Downstream advances PhxBringup's source build marker from 40 to 41. Only the
compute queue gains this ring prefix, once per native submission and before
all user IBs:

```text
ACQUIRE_MEM: 0xc0065800, 0, 0xffffffff, 0x00ffffff, 0, 0, 10, 0xc3b1
INDIRECT_BUFFER ... [one or more unchanged IB packets]
RELEASE_MEM ...     [unchanged sequence and completion packet]
```

`0xc3b1` requests the reviewed GLI/GLK/GLV/GL1/GL2 invalidation,
GL2 writeback, and GLM invalidate/writeback fields. The ring's reservation,
overflow check, committed write pointer and per-submission history all include
the eight added dwords. Graphics retains its existing packet stream.
The header's compile-time `PHX_IB_FETCH_SYNC=0` control omits both the prefix
and its space reservation; downstream source defaults to 1. Values 2 and -1
are refused at compile time. This is not a runtime tuning knob.

No ABI, user-IB contents/address, CPU cache maintenance, PTE/cache mode,
fence event, completion policy, wait accounting, doorbell range, scheduler
configuration, clock, power or SDMA change is part of this correction.
Downstream's previously existing wait change remains present but unaccepted;
it must not be mixed into an original-build34 hardware comparison.

## Isolated original-build34 comparison

`tools/upstream34_layout/ib_fetch_sync.py` reads the fixed default checkpoint
`64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`, validates its kernel-source hash,
and makes four reversible localized replacements: include, build marker,
space accounting, and prefix emission. All other original kernel bytes remain
unchanged. It exports the applicable original sources and license notices and
adds the same new header. This generated candidate reports **build42**, not
original build34 or downstream build41.

Both build42 policies use identical source and differ only in their explicit
compile-time `PHX_IB_FETCH_SYNC=0/1` value. This pair excludes downstream's
wait fix, ownership changes and MEC-range experiment. It does not modify the
default worktree, installed image or ordinary bring-up helper.

```sh
make test-ib-fetch-sync
python3 tools/upstream34_layout/ib_fetch_sync.py build/ib-fetch-compile-example --sdk /path/to/MacKernelSDK
```

Outputs must not exist. The recipe compiles, ad-hoc signs and verifies x86_64
kexts only. It never installs, loads, initializes, runs a native check/probe or
reboots. The separate manual workflow follows the same compile-only boundary
and uploads no artifacts. Do not run the legacy build34 diagnostic on build42
by weakening its admission checks; a future controller must bind an expressly
reviewed build42-compatible HOLD probe and exact images.

## Validation and hardware gate

Actual-method tests independently check the full packet bytes, one prefix per
compute submit, unchanged graphics, multiple/max IBs, canonical upper VA,
ring wrap, exact memory changes, history, writeback and doorbell values, and
insufficient ring-space refusal. Both downstream and the generated build34
submission bodies run in a fake aperture/VM-binding class. A fixed previous
actual submission body fails the specific new compute-prefix assertion;
that is an offline packet regression, **not reproduction of the GPU wrong value**.
Control and sync packet matrices use ASan/UBSan. No fake cache outcome is
treated as proof of a real coherency repair.

Local actual-method validation passed 72 packet/control scenarios and 380
queue/VM/context/BO scenarios (104/71/123/82). The previous compute packet
failed the specific new assertion as expected, and two nonboolean compile
policies were refused. All 757 Python tests passed under Python 3.13.18.
Downstream build41 and both generated build42 policies
compiled, were ad-hoc signed, and passed signature and x86_64 verification.
Their three shadow-warning messages match the earlier unchanged baseline.
The build42 control binary contains no new prefix constant; its sync peer
contains the complete prefix. These are compile/host results, not execution
or acceptance results. No manual workflow has been dispatched.

The hardware acceptance condition remains the same reused-IB workload: control
must reproduce the observed wrong value; sync must then pass full-buffer
comparisons with rewritten/reused slot 0 under a separate fresh scope and
successful recovery. A two-dispatch pass alone cannot accept the wait fix,
96-dispatch/concurrent/background-load gate, desktop stability or FPS.
An inconclusive control stops the comparison. A bad output, timeout, uncertain
retirement or cleanup error must retain resources and stop further submission.

No previous one-use packet may be replayed. A future boot/load trial needs new
exact-image and fresh-boot admission, independent bounded recovery and explicit
rollback to the original build34/GPU-off state. Until that gate passes, retain
the source candidate on downstream and do not promote it to default.

Source rollback is a normal revert of this isolated change. There is no newly
installed driver change to undo. Source-bound validation is recorded in
[the validation record](validation/ib-fetch-sync-20261116.json).
