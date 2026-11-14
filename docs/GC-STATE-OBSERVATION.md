# Fixed GC state observation before further selector diagnosis

Status, 2026-11-14: **source/CPU-validated diagnostic candidate; native IOKit
binary compiled, never run on the GPU or installed**. The current boot remains
terminal after the [first-KIQ dual-zero result](
DESKTOP-SELECTOR-PREFLIGHT.md#system-domain-target-result). This tool does not
reopen that scope or establish a driver fix.

## Source difference worth measuring

The executed `gfx-power-sequence` finishes after firmware loading, RLC autoload,
the acknowledged IMU request, and a bounded CP_STAT/RLC_BOOTLOAD_COMPLETE check.
Those observations do not certify all graphics initialization prerequisites.
In the pinned Linux PSP path, `gfx_v11_0_hw_init` continues through GFXHUB,
golden registers, constants, RLC resume and CP resume after the autoload wait.

One specific difference is measurable without changing it:
`gfx_v11_0_constants_init` programs the GRBM_CNTL READ_TIMEOUT field to `0xff`
before its VMID-selection loop. The current checked firmware/power path does
not perform that constants stage, and the failed desktop preflight does not
record GRBM_CNTL. Its actual target value is unknown. Neither this difference
nor a reset/halt bit alone establishes why GRBM_GFX_CNTL read back zero. Do not
copy the Linux initialization sequence, alter the timeout or clear reset/halt
bits based only on this source comparison.

The source review uses Linux commit
`7d0a66e4bb9081d75c82ec4957c50034cb0ea449`. All eight files in the existing
[selector manifest](validation/linux-mes-selector-reference.json), plus the
two GC register headers in the [queue manifest](
validation/linux-mes-queue-reference.json), were rechecked against their cached
SHA-256 pins. Register offsets, base indices and the GC 11.0.1 bootload override
were checked individually. The AMD MIT-style notices were reviewed; no Linux
implementation bodies or whole headers were copied. The observer shares the
existing nullarc transport under its existing component licences.

## Candidate interface and fixed scope

[`tools/phxctl/gc_state_observe.c`](../tools/phxctl/gc_state_observe.c) promotes
the earlier private 18-register reset observer into reproducible source, adds
GRBM_CNTL, and validates the complete numeric PSP layout. The argument contract
is `gc-state-observe configured|tmr-ready <absolute-private-output.partial>`.
There is no automatic phase selection, arbitrary address, reset, power request,
selector write or initialization option.

The only scalar IOKit command in the observation path is the existing ABI
handshake. It reads bootstrap metadata once before and once after exactly
19 fixed register observations:

| Purpose | Register names |
| --- | --- |
| Always-on positive controls | PSP_INITIALIZATION_STATUS, RCC_CONFIG_MEMSIZE |
| General GC state | GRBM_STATUS, GRBM_STATUS2, GB_ADDR_CONFIG, CP_STAT |
| Selector and MES state | GRBM_GFX_CNTL, CP_MES_CNTL |
| RLC and IMU state | RLC_CNTL, RLC_STAT, RLC_PG_CNTL, RLC_CGCG_CGLS_CTRL, RLC_GPM_STAT, GC 11.0.1 RLC_RLCS_BOOTLOAD_STATUS, GFX_IMU_SCRATCH_0 |
| Reset, halt and timeout observations | GRBM_SOFT_RESET, CP_ME_CNTL, CP_SOFT_RESET_CNTL, GRBM_CNTL |

It never calls the desktop reservation, seal, claim, VRAM, doorbell, firmware or
SMU interfaces. It includes the existing `mesboot.c` for its checked transport
and explicit published-geometry gate; it does not dispatch the renamed legacy
CLI entrypoint. Tests assert the allowed selectors, exact independent register
list and ordering, and reject every unexpected call.

`configured` requires precisely configured-only bootstrap flags and no TMR
bytes. `tmr-ready` requires precisely configured/ring/TMR flags and a nonzero
TMR size within capacity. Both reject GPU-active, faulted or unknown flags,
invalid layouts, geometry mismatches, changed metadata, all-ones register data,
transport errors and wrong reply lengths. The PSP ready control and memory-size
control must pass. Zero-valued GC fields remain valid observations when those
positive controls pass; they are not relabelled as readiness.

## Output, failure and execution boundary

The output must be an absolute, previously nonexistent `.partial` path. The
collector requires administrator identity and creates it exclusively with mode
0600 and final-component symlink refusal. The caller must protect the parent
directory. It buffers observations until metadata comparison and checked
service close succeed, then writes, flushes, synchronizes and closes the file.
The JSON says `observation_only: true`; success means a completed observation,
not a graphics readiness result. The caller must require exit zero as well as
complete output; a file surviving an output error is not an accepted receipt.

Raw output is private diagnostic material and must stay ignored. Do not commit
it, publish it as an artifact, or add the candidate binary to existing kext or
RADV artifact workflows. Before any new hardware run, an external, separately
reviewed request must bind a fresh boot, phase ordering, exact signed inputs,
private output locations, a finite invocation budget and independent recovery.
The collector does not supply those admission or watchdog mechanisms. A
synchronous driver call can still stall; the fixed read count is not a wall
clock timeout.

The next experiment should observe a fresh configured baseline and the same
fixed fields at reviewed PSP/firmware/IMU boundaries, without adding a selector
probe or changing timeout/reset/halt values. This is an unselected future
design, not an active request. Do not run the collector, repeat firmware/power,
or initialize the GPU on the current stopped boot. Rollback of this source
candidate is simply not selecting it; no installed component was changed.

## Verification

Seven actual-collector CPU test methods pass under ASan/UBSan. They cover both
explicit phases and reference/relocated geometry, every register position's
transport/length/all-ones failure, invalid metadata, drift, positive controls,
exclusive output, privilege, ABI and checked-close failures. Every case uses
fake IOKit; unexpected mutation requests abort the fixture.

The native x86_64 IOKit build also passes with warnings treated as errors. Its
binary was compiled privately and never executed. The production `mesboot.c`,
`phxctl.c`, kernel, installed tools and startup configuration remain unchanged.
The earlier full-suite result is historical and was not rerun for this scoped
collector change. See the [sanitized source validation](
validation/gc-state-observer-20261114.json).
