# Fixed GC state observation before further selector diagnosis

Status, 2026-11-14: **a separately admitted fresh-boot experiment completed a
configured baseline, one firmware/power command and a TMR-ready observation**.
Both observer invocations returned zero. READ_TIMEOUT changed from `0` to
`0x30`; CP/MES halt fields also changed. The experiment is consumed and this
new boot is terminal for further GPU work. See [the target observations](
#fresh-boot-target-observations). The earlier [first-KIQ dual-zero scope](
DESKTOP-SELECTOR-PREFLIGHT.md#system-domain-target-result) remains consumed;
this observation experiment did not write a selector or establish a driver fix.

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
record GRBM_CNTL. Its value during that failed preflight remains unknown; the
later fresh-boot experiment below measured `0x30` after firmware/power. Neither this difference
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

The initial design proposed observations across reviewed PSP/firmware/IMU
boundaries. The later admitted experiment used two boundaries only: configured
baseline and completion of the existing combined firmware/power command. It
did not capture intermediate PSP, firmware or IMU snapshots. That request is
now consumed. Do not run the collector, repeat firmware/power, probe selectors
or initialize the GPU on the current stopped boot. No installed component was
changed; retain the existing off marker and use a separately reviewed fresh
boot for any future hardware experiment.

## File-only phase comparison

[`tools/gc_state_compare.py`](../tools/gc_state_compare.py) compares collected
files without launching a process, opening IOKit, making network requests or
changing hardware. It is preparation for a future experiment, not a caller of
the collector. It does not deploy anything or create a live experiment scope.

An external capture runner must first accept each collector invocation's exit
zero and complete, synchronized output. It can then write a private manifest
with exactly `schema: 1` and an `observations` array. Each array entry has exactly
four fields: `stage`, `file`, `sha256`, and `exit_status`. Stages must be an
unrepeated prefix of `baseline`, `psp`, `firmware`, `power`; filenames must be
distinct `.partial` basenames in the manifest's directory. Digests are SHA-256
of those exact file bytes, and reported exit statuses must be integer zero.
For example, this Python shape describes a single already-accepted baseline;
the runner must supply the actual digest rather than a sample value:

```python
manifest = {
    "schema": 1,
    "observations": [{"stage": "baseline", "file": "baseline.partial",
                      "sha256": accepted_baseline_sha256, "exit_status": 0}],
}
```

Invoke the analyzer only on private files, for example with the general form
`python3 tools/gc_state_compare.py <private-manifest.json> <absolute-private-report.partial>`.
The output must not already exist. It is created exclusively with mode 0600
and synchronized before successful exit. Protect the parent directory and keep
all input/output files ignored; the report contains raw register observations.
It is not a public validation record or a new artifact-upload exception.

The analyzer rejects unknown/duplicate JSON keys, oversized/nonregular inputs,
symlinked input files, wrong schemas or phases, nonzero/malformed exit receipts,
digest drift, changed memory-size controls, and any register identity, index,
order, range or positive-control mismatch. The actual fake-IOKit collector's
output is also checked against this independently specified 19-register contract
in both modes and both published geometries. A valid all-zero GC observation
with passing always-on controls remains valid data.

For each phase it preserves raw values, reports every changed register and XOR
against the preceding phase, and decodes the reviewed fields of GRBM_CNTL,
CP_ME_CNTL, CP_MES_CNTL, GRBM_SOFT_RESET and CP_SOFT_RESET_CNTL. Undecoded bits
remain visible. The CP/RLC completion bit observation is labelled separately;
it is not graphics readiness. The report always says that hardware readiness,
physical cause, and boot/capture provenance are unproven. Manifest order and
exit statuses are caller assertions: hashes bind bytes, not a boot identity or
truthful capture. This file analysis cannot replace the external experiment's
fresh-boot, input-signature, phase, budget or recovery checks.

## MES ordering review

An additional hash-verified review of pinned `mes_v11_0.c` confirms that
`mes_v11_0_enable(true)` sets MES pipe reset bits before selecting ME3 for
firmware program counters. Its direct-load helper first disables MES before
its own ME3 selection. The local `mes_start` also writes reset before its ME3
entrypoint selections; however, `desktop_command` checks KIQ/scheduler queue
idleness before reaching GART and `mes_start`. The failed preflight terminates
at that earlier KIQ selection.

This ordering difference does not prove reset-before-selection is a hardware
requirement or explain the dual-zero result. The Linux GFX path has already
run additional GFXHUB/constants/RLC work before CP resume calls MES KIQ init;
copying only a reset write would not reproduce those prerequisites. The
reviewed upstream `full.sh` similarly reaches its setup writes only after
`bringup5.sh`; it is not an admission-safe replacement for the checked path.
Do not move the reset ahead of the idle guard or execute the legacy scripts
on this evidence. The immediate next diagnostic remains observing phase
boundaries on a separately admitted fresh boot, with no selector/reset write.

## Verification

Seven actual-collector CPU test methods pass under ASan/UBSan. They cover both
explicit phases and reference/relocated geometry, every register position's
transport/length/all-ones failure, invalid metadata, drift, positive controls,
exclusive output, privilege, ABI and checked-close failures. Every case uses
fake IOKit; unexpected mutation requests abort the fixture.

At the source milestone, the native x86_64 IOKit build passed with warnings
treated as errors and was compiled privately without execution. A later signed
copy was executed only in the separate target experiment below. The production `mesboot.c`,
`phxctl.c`, kernel, installed tools and startup configuration remain unchanged.
The earlier full-suite result is historical and was not rerun for this scoped
collector change. See the [sanitized source validation](
validation/gc-state-observer-20261114.json).

The later file-comparison addition passes eight synthetic-file test methods.
Seven actual-collector sanitizer methods, 31 desktop/native include methods,
and 30 desktop-startup methods were rerun with zero failures/errors/skips:
76 focused methods in total for that addition. No native target-linked binary
was run, recompiled or deployed by the comparison change. Its field/offset
checks and preservation limits are recorded separately in [the comparison validation](
validation/gc-state-comparison-20261114.json).

## Fresh-boot target observations

After the owner explicitly requested a reboot and then continued, a changed
boot identity was verified on macOS 26.7.2, build 25G332. Metadata admission
matched the expected build-39 provider and loaded image, firmware framebuffer,
off marker and absent display arming; PhxAccel remained absent. All 11 native
source dependencies and the original unsigned binary hash matched the prior
validated candidate. A private copy was ad-hoc signed and passed strict
verification. Neither an installed tool nor a driver was replaced.

A distinct max-one request bound the fresh boot, exact commands, 49 input
pins, 12 recovery pins, 90-second work budget and 120-second independent
system-domain watchdog. All three historical receipt sets (188, 29 and 97
files) matched before and after. The root watchdog became ready before any
native command. One configured observer, one unchanged `gfx-power-sequence`
and one TMR-ready observer each returned zero with their required completion
markers. Both positive controls passed and memory-size controls agreed.

| Observed field | Configured baseline | After firmware/power |
| --- | --- | --- |
| GRBM_CNTL.READ_TIMEOUT | `0x00` | `0x30` |
| CP_MES_CNTL.MES_HALT | `0` | `1` |
| CP_MES_CNTL pipe reset/active fields | all `0` | all `0` |
| CP_ME_CNTL CE/PFP/ME halt fields | all `0` | all `1` |
| GRBM_SOFT_RESET | `0` | `0` |
| CP_SOFT_RESET_CNTL | `0` | `0` |
| GRBM_GFX_CNTL, observed without a write | `0` | `0` |
| CP_STAT zero and RLC bootload-complete bit | not both observed | both observed |

All 17 GC fields were zero at baseline with passing always-on controls; 11
were nonzero after firmware/power. These are completed observations, not a
test of selector writability, acceleration or a new reproduction of the KIQ
failure. In particular, `0x30` is nonzero and the source's `0xff` difference
alone does not prove a timeout defect. Halt bits do not independently establish
why a selector write failed on another boot. No timeout/reset/halt register
was changed by the observer. The existing firmware/power command has its own
mutations and is not included in that read-only statement.

The terminal result dismissed the watchdog normally. Exact system-job readback
showed one run and exit zero; the job was removed and absence verified. No
recovery reboot was requested. The scope retains 187 private receipt files.
There was no selector write, desktop reservation, GART/MES/queue initialization,
seal, claim or display step. The collector's fixed request counts are derived
from reviewed source and fake tests, not independent live GPU tracing.

Twenty-seven runner file/mock methods and 15 shared collector/analyzer methods
passed in this turn, with zero failures/errors/skips. The actual collector
methods used ASan/UBSan and fake IOKit; the full suite was not rerun. Deadline
recovery is CPU-tested; a hardware deadline-reboot recovery was not exercised.
No additional hardware work is authorized by the result. Continue interpretation
offline and preserve the terminal boot until a separately reviewed next
experiment. See the [sanitized target record](
validation/gc-phase-observation-target-20261114.json).

The subsequent [VMID-only control candidate](DESKTOP-VMID-PREFLIGHT.md) tests
a separate selector field without changing timeout/reset/halt state. It is
source/CPU-only and has not been run on this terminal boot. A future result
must not be conflated with these completed read-only observations.
