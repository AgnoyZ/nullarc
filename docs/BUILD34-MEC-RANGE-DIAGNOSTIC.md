# Default build34 MEC range diagnostic

Status on 2026-11-16: source and offline tests only. This diagnostic does not
establish a fix for the native reused-IB wrong value, mouse/GUI stalls or FPS.
The default branch remains `upstream34/vram-layout-fix`, with the accepted
A1/A2/corrected-A3 changes. Build41/build42 remain withdrawn.

## Why isolate this upstream lead

Upstream main was rechecked at
[`8aba872560a3c9b7dc7a0ddebfad001c6dddf315`](https://github.com/luuumi-dev/nullarc/commit/8aba872560a3c9b7dc7a0ddebfad001c6dddf315).
Its `src/phxbringup/PhxBringup.cpp` is byte-identical to the default build34
kernel: SHA256
`beffab5dc13e4018ff2ab9f90c82d85c0982ce7e3563e3175999399c7bc083e5`.
Updating to that upstream main supplies no different submission implementation.

[PR #14](https://github.com/luuumi-dev/nullarc/pull/14), reviewed at head
`9f37791bb816092df580f3cb62a9db1e2357fb8f`, remains open and unmerged.
It contains a separate initialization lead: bound the compute doorbell range
before user compute/graphics queue setup. Its CP-idle reports are from other
machines, not proof about this machine's reused-IB failure. Keep its clock,
power, scheduler-mask, timer and other initialization changes out.

The existing original34 range experiment is now available as diagnostic
tooling on the default branch. The production helper, kernel, ABI, waits and
initialization path are unchanged. This is not promotion of the experimental
register writes into ordinary initialization.

## Exact source and operation boundary

`tools/upstream34_layout/mec_range.py` reads fixed default checkpoint
`64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`. It verifies the pinned helper
hashes and, before creating output, compares the current `src/phxbringup`,
`tools/phxctl`, licences and notices with that checkpoint. Any differing or
missing protected file is terminal. It preserves A1/A2/corrected-A3 in their
separate plugin/accelerator source paths.

The generated helper has only two insertion sites: an include/call before
`sched_init()` and an early CLI guard. Reversing those insertions reproduces
the original `mesboot.c` byte for byte. Both policies accept exactly
`kiqsched`; other arguments are rejected before device lookup. Original
build34/ABI 1.12 and VRAM-geometry admission remain intact.

| Explicit compile policy | Additional register operations |
| --- | --- |
| `PHX34_MEC_RANGE_TRIAL=0` | None |
| `PHX34_MEC_RANGE_TRIAL=1` | Write upper (`0x305d`) = `0x450`, verify immediate and separate readbacks; then write lower (`0x305c`) = `0`, verify both readbacks. |

Register addresses are dword indices; range values are byte offsets. The
original GFX doorbell index `0x116` corresponds to byte offset `0x458`, outside
this proposed range. The hook follows original `kiq_init_only()` and precedes
scheduler MQD/resource setup and user queues; it does not precede every queue
in bring-up. Any transport, output-length or readback error prevents scheduler
setup. A failed upper step prevents the lower write. There is no retry or live
rollback of a partially changed GPU.

## Offline checks

```sh
make test-upstream34-mec-range
make test-upstream34-layout
python3 tools/upstream34_layout/mec_range.py build/build34-mec-compile-private --compile
```

Output directories must not already exist. The actual generated C CLI runs
only with synthetic IOKit under ASan/UBSan, linking CoreFoundation without
IOKit. The fixture checks original KIQ order and terminal error paths, then
exits at the first scheduler-MQD write. It does not simulate GPU execution,
CP idle, native submission, retirement or output correctness. Synthetic
build41/build42 identities must be refused; their candidates are never built.

The native build only compiles, ad-hoc signs and checks the architecture and
signature of the two original34 user helpers. Neither binary is executed,
including with invalid arguments. The manual source workflow performs those
offline operations and has no artifact upload, installation or GPU step.
Local validation and source fingerprints are recorded in
[the validation record](validation/build34-mec-default-20261116.json).

On 2026-11-16, all eight source/result checks and 148 actual-C ASan/UBSan
cases passed, with three invalid/missing compile-policy refusals. All 20
original layout/shell regression methods passed without skips. Both native
x86_64 user helpers compiled, were ad-hoc signed and passed signature and
architecture verification; each retains the original unused-`val` warning.
The complete `src/`, production `tools/phxctl/` and licence/notice trees match
the approved checkpoint. These are local offline results; the manual workflow
has not been dispatched and no hardware gate has passed.

## Hardware gate and rollback

All earlier native policy scopes remain consumed. This change does not create
a startup job, arm recovery, install/load a driver, initialize the GPU or
reboot. Do not run the helper as a live register fix or replace ordinary
`mesboot`: this restricted helper alone is not an ownership/recovery protocol.

A subsequent hardware comparison requires a new exact-image original34 scope,
fresh-boot/PCI/OS and inactive-queue admission, an independent bounded recovery
path, unchanged EFI/security baseline and one policy per scope. The control
must establish actual range/CP-idle observations and reproduce the bounded IB
signature. Only its verified result and recovery can permit a separately
authorized treatment. The old consumed trial packets cannot be replayed.

Register readbacks or two successful dispatches do not accept the wait change,
load/concurrency/desktop gates or FPS. Accelerated desktop and wait promotion
remain on HOLD. Source rollback is a normal revert of this isolated tooling
addition; there is no installed change to undo.

The reviewed helper implementation is MIT OR GPL-2.0-only. The generated
AMD-derived headers retain their own MIT notices verbatim; the generator
copies applicable licences/notices from the fixed checkpoint. No firmware,
plugin, third-party implementation body or binary is imported. The full-stack
binary publication block remains in place.
