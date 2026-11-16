# Default build34 MEC range diagnostic

Status on 2026-11-16: separately authorized original34 control and MEC-range
treatment scopes both reproduced the same reused-IB wrong value and completed
recovery. The range-only treatment did not fix this trigger. This diagnostic
does not establish a fix for the native reused-IB
wrong value, mouse/GUI stalls or FPS.
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

### Common routing and read-only observation support

`tools/upstream34_layout/mec_runtime.py` adds pure routing and observation
functions for a separately contained control/trial comparison. Importing it
does not access hardware or launch processes. A rendered router preserves the
environment and sends only `gart`/`mes` to the original34 helper. It requires a
successful external `sample-before` gate before invoking the explicitly chosen
`kiqsched` helper. Other arguments and sampling failures are terminal. The
router cannot provide ownership, image admission, a deadline or recovery by
itself, and must never replace the global production helper.

The strict observation parser accepts the exact ordered original34 `regs`
output for dword addresses `0x305d`, `0x305c`, `0x2004`, `0x2002`, `0x2087`,
`0x219f` and `0x21a0`. Missing/reordered/error output, all-ones reads and zero
GRBM status are rejected. The summary records range and status stability only;
it always declines to establish global GPU idle or IB integrity. No unverified
CP bit mask is used. The planned common observations are after original
GART/MES and before KIQ/user queues, then six samples after original
compute/graphics/adoption and before the native probe. This observation delay
belongs to both policies and must not be mistaken for a range-only fix.

`make test-upstream34-mec-runtime` passed all seven CPU-only test methods on
2026-11-16. It executes generated routers only with fake helpers, covering
policy selection, original stages, preserved environment, path quoting,
argument rejection and terminal sampling/helper failures. Separate private
mock regressions covered deadline clocks, six concurrent recovery requests
with one mock dispatch, no recovery-boot GPU retry, control-only selection,
private `HOME` and stopping before the native probe after observation failure.
Four original34 user helpers compiled and passed signature/architecture checks;
none was executed during that offline preparation. See the separate
[preparation record](validation/build34-mec-runtime-preparation-20261116.json).
These checks do not arm a hardware trial or establish a GPU result.

### Separate hardware admission

All earlier native policy scopes remain consumed. The tooling additions by
themselves do not create a startup job, arm recovery, install/load a driver,
initialize the GPU or reboot. Do not run the helper as a live register fix or
replace ordinary `mesboot`: this restricted helper alone is not an
ownership/recovery protocol.

A subsequent hardware comparison requires a new exact-image original34 scope,
fresh-boot/PCI/OS and inactive-queue admission, an independent bounded recovery
path, unchanged EFI/security baseline and one policy per scope. The control
must retain actual range/status observations and reproduce the bounded IB
signature. Register samples alone cannot establish CP idle. Only its verified
result and recovery can permit consideration of a separately authorized
treatment; the control cannot start that treatment. The old consumed trial
packets cannot be replayed.

Register readbacks or two successful dispatches do not accept the wait change,
load/concurrency/desktop gates or FPS. Accelerated desktop and wait promotion
remain on HOLD. Source rollback is a normal revert of this isolated tooling
addition; there is no installed change to undo.

The reviewed helper implementation is MIT OR GPL-2.0-only. The generated
AMD-derived headers retain their own MIT notices verbatim; the generator
copies applicable licences/notices from the fixed checkpoint. No firmware,
plugin, third-party implementation body or binary is imported. The full-stack
binary publication block remains in place.

## Single-use original34 control result

The owner continued a new bounded original34 control on 2026-11-16 after the
offline preparation. This scope used default commit
`a783a166739a8408fdbc3bda4be4d9b58c2f3f48`, the existing exact original34
driver image and the previously frozen original34 two-dispatch control probe.
The actual OS was macOS 26.7.2, build `25G332`. No driver was installed or
loaded by the experiment, and the range-treatment helper was not run.

Original compute, graphics and queue adoption passed. The native probe fully
verified its first guarded dispatch, then failed the second at allocation
offset `0x2010` (pass index 1): actual `0xde`, expected `0xdf`. It immediately
entered HOLD and retained its connection/mappings until recovery. This is the
same bounded reused-IB signature observed before the new common sampling.
There was no GPU retry, CPU-load trial, concurrent client, display takeover or
FPS test.

One range/status observation preceded KIQ/user-queue setup and six followed
the original compute/graphics/adoption checks. The observed range remained
unchanged across those samples and did not match the proposed treatment
range. Post-initialization GRBM status was stable. These are bounded
observations, not evidence of global CP/GPU idle, a doorbell-range root cause
or correct native IB execution. In this control, the common observation delay
did not prevent the mismatch.

Exactly one recovery reboot returned to the same original34 image with
GPU-off and the firmware framebuffer. The independent result, retirement and
final readbacks passed: the consumed startup job was removed, no probe or
shutdown remained, recovery-boot GPU calls were zero, and no additional trial
started. All 347 EFI files (including 148 Microsoft files), 46 protected files,
two protected links, OpenCore configuration, security settings and kernel
collections were unchanged. No new matching WindowServer/kernel/GPU-restart
diagnostic report appeared. This is not a desktop-stability acceptance.

Two preparation/reporting errors did not change the hardware sequence. An
incorrect test-receipt path was rejected before root-packet creation and was
corrected with a CPU-only regression. After independent result assertions and
the exclusive result write, a local export failed because a loop variable
shadowed the export-stage name. A separate read-only check verified the
existing receipt against the frozen inputs and mismatch evidence, completed
the missing export, and allowed retirement; the GPU trial and result-writing
stage were not repeated. The original frozen controller/verifier was retained.

See the [sanitized control record](validation/build34-mec-control-20261116.json).
All raw logs, register samples, firmware, binaries and machine identifiers
remain private. This control is consumed. Any MEC-range treatment needs a
different explicit single-use scope with the same common observations and an
independent recovery path; it cannot be started by this control. IB repair,
wait promotion and accelerated desktop remain on HOLD.

## Single-use MEC-range treatment result

After the control was retired, the owner explicitly authorized a different
single-use treatment: one original34 initialization, at most two guarded
dispatches and at most one recovery reboot. It used default commit
`fef96cc64dc82ce2cf7c1b98aaa0f1bef025c60a`, the same original34 driver image,
frozen native probe, original initialization stages and common observations.
The actual OS remained macOS 26.7.2, build `25G332`. No driver deployment,
global-helper replacement, CPU load, concurrent client or display takeover
was performed.

The helper's only treatment was the proposed upper/lower MEC range writes
with immediate and separate readbacks. The pre-treatment range matched the
control. All six post-adoption samples retained the proposed range, different
from the control; original compute, graphics and adoption checks also passed.
Nevertheless, native pass 0 passed and pass 1 failed at `0x2010`, actual
`0xde`, expected `0xdf`: exactly the control's mismatch. The native probe
entered HOLD without a retry. The treatment does not establish global CP/GPU
idle, and range readbacks do not establish native integrity.

One recovery reboot returned to the original34 GPU-off/firmware-framebuffer
state. Independent result and final checks passed, and the consumed job was
removed. The retirement tool call timed out after 30 seconds, so its completed
exclusive retirement receipt was observed before the final check; retirement
and GPU work were not retried. EFI's 347 files (148 Microsoft files), 46
protected files, two links, security settings and kernel collections remained
unchanged. No new matching diagnostic report was found. Raw evidence remains
private; see the [sanitized treatment record](validation/build34-mec-treatment-20261116.json).

The private controller checks included rejection of an unexpected pre-range,
refusal to submit if the target range was not retained, and the existing
single-use recovery/HOLD protections. Three CPU-only executions of the actual
verifier result/export code covered mismatch, bounded PASS and an incomplete
initialization, including a regression for the previous export-stage shadowing
error. These are containment checks, not simulated hardware validation.

For this specific reused-IB trigger, the measured range-only intervention is
insufficient. This does not test or reject every other change in upstream
PR #14. Do not adopt the range writes into ordinary initialization or claim
an IB, GUI-stability or FPS fix from this result. Both new scopes are consumed;
wait promotion and accelerated desktop remain on HOLD.
