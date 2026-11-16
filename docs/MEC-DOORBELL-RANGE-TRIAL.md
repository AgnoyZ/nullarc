# Original build34 MEC doorbell-range source candidate

Status on 2026-11-16: **offline candidate only; no hardware trial or default
promotion**. The [upstream review](UPSTREAM-SOLUTION-AUDIT-20261116.md) ranked
the range-only subset of nullarc PR #14 first for investigation. It is not an
established fix for the native IB mismatch, background-load stutter or FPS.

## Fixed source and one experimental change

`tools/upstream34_layout/mec_range.py` reads original build34's helpers at
default checkpoint `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`, which already
contains A1/A2/corrected-A3. It verifies all four source-input SHA256 values
before creating a new output directory and retains the applicable notices.
It does not modify that branch, its worktree, the installed helper or the kernel.

Reference: [PR #14 at reviewed head
`9f37791bb816092df580f3cb62a9db1e2357fb8f`](https://github.com/luuumi-dev/nullarc/pull/14).
The register values and upper-before-lower order are the reviewed facts; the
checked implementation is downstream code. phxctl/phxbringup remain MIT or
GPL-2.0-only; the two AMD-derived headers retain their own MIT notices verbatim.
No plugin, firmware, binary or other PR implementation is imported.

The generator makes exactly two reversible source insertions: include/call the
trial header immediately before `sched_init()`, and add common CLI admission
before device lookup. The rest of the pinned helper is byte-for-byte preserved,
including validated VRAM geometry, ABI/build checks, transport checks, MES
masks, timer, queue packets, compute/graphics checks and adoptions.

Both compiled policies accept only exactly `kiqsched`; every other command or
argument count is refused before looking up the device. There is deliberately
no native `--check` mode. Earlier bring-up stages would still require the
unchanged original helper in a later separately reviewed controller.

| Build policy | Additional operations at the start of `sched_test()` |
| --- | --- |
| `PHX34_MEC_RANGE_TRIAL=0`, control | None |
| `PHX34_MEC_RANGE_TRIAL=1`, range trial | Write `CP_MEC_DOORBELL_RANGE_UPPER` (dword register `0x305d`) to `0x450`; validate the write's returned readback and a separate read. Then write `LOWER` (`0x305c`) to `0`; validate both readbacks. |

The values are byte offsets. The GFX doorbell index `0x116` represents byte
offset `0x458`; it must remain outside the compute range. No `CP_MAX_CONTEXT`,
`CP_DEVICE_ID`, clock, power, SDMA, GFXOFF, scheduler-mask or timer change is
included. The treatment includes two new register writes and two independent
reads, in addition to checking the writes' own returned readbacks. It does not
add a pre-existing-state register capture or establish GPU quiescence.

This hook runs after the original `kiq_init_only()` but before scheduler MQD
construction, hardware-resource setup and user compute/graphics queue creation.
It is not a change before every queue in the entire bring-up. An IOKit failure
or wrong output length exits with status 74. A mismatched immediate or separate
readback exits with status 75. A first-step refusal prevents the lower write;
any refusal prevents scheduler initialization. There is no retry or attempt to
restore partially changed registers on a live GPU.

## Offline validation and compilation

On macOS, use a fresh output directory for each invocation:

```sh
python3 -m unittest discover -s tests -p test_upstream34_mec_range_runner.py -v
python3 tools/test_upstream34_mec_range.py --out build/mec-range-host-example
python3 tools/upstream34_layout/mec_range.py build/mec-range-compile-example --compile
```

The actual generated C CLI is compiled with ASan/UBSan and synthetic IOKit
functions, linking CoreFoundation but **not IOKit**. Separate processes cover
both policies, argument/geometry/ABI refusal, KIQ transport refusal, both new
register writes, each returned length, immediate readback and separate read.
The fixture checks the actual upper/lower order, registers, values and unchanged
KIQ prefix: two reads, 23 register writes and 1,598 VRAM writes. It stops at the
first scheduler-MQD write. It neither models scheduler/GPU execution nor proves
CP idle, output integrity, frame rate or desktop stability.

The Python tests check fixed-source drift refusal, the exact two-insertion
round trip, output-directory refusal and rejection of misleading test results.
The three fixed-source unit methods skip only when their commit is unavailable
in shallow history; the actual-CLI target requires that object and does not skip.
Native compilation builds/signs two x86_64 helpers with explicit policy flags;
neither native binary is executed, including with an invalid argument.
Missing/nonboolean policy definitions fail compilation. The manual
`upstream34-mec-range.yml` workflow runs these offline checks and existing
layout/shell regressions, without uploading artifacts or running a native helper.

The local preparation passed all 140 actual-C ASan/UBSan cases (60 control,
80 range trial), three invalid/missing-policy compile refusals and seven
Python source/result checks. The existing layout/shell tests passed 19 methods;
the existing desktop- and startup-evidence checks each passed nine methods.
Both native x86_64 helpers compiled, were ad-hoc signed and passed signature/
architecture verification. Each retained only the same original unused-`val`
warning observed in a separate syntax-only compilation of the pinned baseline.
The new manual workflow has not been dispatched; these are local results.

Results and source fingerprints are recorded in
[the preparation record](validation/upstream34-mec-range-preparation-20261116.json).

## Hardware boundary and rollback

This preparation does not create a launchd job, install a helper/kext, initialize
the GPU, submit a dispatch, reboot or arm a hardware trial. All earlier native
IB policy scopes remain consumed and cannot be reused. The original build34
kernel, default branch and A1/A2/corrected-A3 remain unchanged; the elapsed-time
wait candidate and accelerated desktop remain on HOLD.

A later hardware controller must bind the exact source/binary and original
build34 image, verify fresh-boot/PCI/OS identity and inactive queues, establish
one-use headless containment/recovery, and preserve the EFI/security baseline.
It must select one policy per fresh scope. First establish a control's observed
range/CP-idle state and reproduce the bounded native-output signature; compare
the isolated range treatment only after the control's result/recovery checks.
Readbacks alone are not permission to claim CP idle or another dispatch.

Do not run the generated helper as an ad hoc live register fix or replace the
ordinary `mesboot` with it: it rejects the other bring-up commands and is not a
standalone ownership/recovery protocol. There is no installed change to undo.
Source rollback is a normal revert of this isolated recipe/test addition;
private generated files are disposable build outputs.
