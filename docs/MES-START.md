# Firmware-profile MES start: hardware execution unverified

Patch `0014-profile-mes-start.patch` replaces the actual `mesboot mes` command's
single hardcoded instruction entrypoint with independently generated scheduler
and KIQ metadata. It checks the existing GART mapping before resetting MES,
checks both programmed entrypoints before activation, and bounds control-state
polling. It does not submit a scheduler packet or prove firmware execution.

## Metadata and source

`firmware_manifest.py` derives the 64-bit MES instruction start from little-endian
header words at byte offsets 56 and 60, after checking the whole-file hash,
size, header/IP version and component bounds. Zero and unaligned values fail.
The existing nine local firmware files were re-inspected; their identities and
component metadata are unchanged. The revised audit records only additional
MES start metadata and the current parser hash. No firmware bytes are published.

`firmware_profile.py` binds pipe 0 to `gc_11_0_1_mes_2.bin` and pipe 1 to
`gc_11_0_1_mes1.bin`, rejecting missing/invalid start metadata. The generated
`phxFirmwareMes` array retains the per-pipe file index and 64-bit instruction
address. Both reviewed files currently encode `0xfffffffff0005000`; this
coincidence is not a reason to share a hardcoded PC. Header generation and tests
also cover distinct addresses. The existing source provenance hashes the
generated profile, including these new fields.

Linux commit `7d0a66e4bb9081d75c82ec4957c50034cb0ea449` was inspected for the
MES v1 header, per-pipe filename selection, `uc_start_addr >> 2`, reset/activate
ordering and register masks. `validation/linux-mes-start-reference.json`
records the reviewed source hashes. AMD MIT-style notices were inspected;
validation and tests are independently written, and no full Linux bodies or
headers are copied into the implementation.

## Actual command

```text
mesboot mes <virtual-base> <mapped-bytes> <table-offset> <default-page-offset>
```

These are the explicit parameters used by the preceding successful GART setup,
not an instruction to choose arbitrary addresses. Argument-free `mes` now fails
before service lookup. The command:

1. Validates arguments and both generated entrypoints; rejects enabled
   `PTE_SYS`, `FAULT_DEFAULT` and `MESBOOT_MC` overrides before opening IOKit.
2. Uses one ABI-checked connection and selector 116; requires valid PSP/TMR
   metadata, no adopted GPU queue or PSP fault, and a fitting GART layout.
3. Requires CP/RLC boot-readiness observations, twelve matching GART address
   registers, flat/enabled context 0, first/last PTEs, first padding entry when
   present, and the default-page prefix. These checks share the actual GART
   command's readback helpers without changing its sequence.
4. Rejects any of the four active MES pipe bits, all-ones control reads, or a
   nonzero GRBM selection before the first register write.
5. Sets pipe 0/1 reset bits while retaining the initial control value. Selects
   each pipe, checks both the kernel's immediate write readback and a subsequent
   selector read, writes its own shifted PC low/high words and
   checks both readbacks. Checks restored idle selection before activation.
6. Writes the two-pipe activation value, requests a 500-us initial delay and
   checks active/reset/halt fields for at most 1000 samples, requesting 1-ms
   delays after incomplete samples. All ones, transport/shape failures, delay
   errors other than EINTR, timeout and close errors terminate with failure.
7. Reports only programmed entrypoints and activation register observations,
   explicitly leaving scheduler execution unverified.

## Verification and limits

The actual staged CLI is included in `tests/test_mes_start.c`. The harness checks
the register-write sequence, preservation of the initial halt bit during reset,
per-pipe bank selection and address words. Two builds run every case: one with
the audited metadata and one substituting distinct synthetic 64-bit entrypoints.
Cases cover all nine register writes, all 25 reads on immediate completion,
both entrypoint readbacks, GART prerequisites, all four VRAM reads, wrong pipe,
stuck reset/halt, all ones, delayed/absent activation, EINTR and close failures.
No VRAM writes, doorbells, adoption calls or scheduler submissions are accepted
by this harness. Python checks validate termination accounting and false-success
rejection.

Run `41151681907`, code `17763be`, passed 145 Python tests and all 212 MES
actual-CLI cases under ASan/UBSan, plus 319 GART, 76 kernel-method, 114 firmware
sequence and 158 GFX-power regression cases. All MES/GART operation counts and
case sets were independently checked; CLI/kernel method hashes match the staged
source and all fourteen patch/six shared-header hashes match the exact Git
commit. Evidence: `validation/ci-17763be-mes-start.json`.

Native job `124389642450` passed the real-tool compilation/preflight step.
That observation comes from job-step metadata, not native artifact hashes.
The full native build is still running; no full-build pass is claimed here.

This still needs target validation. Snapshot and readback checks do not acquire
exclusive hardware ownership or prevent concurrent raw-debug clients. They do
not prove the resident firmware matches the generated metadata, that all GART
entries translate correctly, or that the firmware has executed any instruction.
The control register can echo activation without scheduler progress. Partial
failures have no automatic rollback; re-running after an error is unsupported.
Legacy queue/MQD/scratch offsets remain unresolved and must not be automatically
chained after this command. Patch 0015 adds a separately checked, explicitly
relocated scheduler-only query path (`MES-QUEUE.md`), but does not resolve memory
ownership or the legacy compute/gfx queue layout. No deployment or working-EFI
change is performed.

## Later target stop and selector diagnostics, 2026-11-12

The separately authorized target test of userspace source `010ffff` reached
MES reset, then stopped on the first pipe-selection readback. No instruction
entrypoint, activation, scheduler queue or shader submission followed. The
earlier command discarded the kernel's immediate selector write readback; a
later read-only query returned zero, which does not establish the value at
the failure boundary. The target boot is terminal for initialization and
must not be retried. Sanitized evidence is in
`validation/legacy-boot-staged-target-20261112.json`.

The subsequent diagnostic change retains every existing readback guard and
also checks the immediate kernel write readback at both pipe selections and
the restored idle selection. On mismatch it reports expected, immediate and
subsequent values before the existing terminal error. It adds no register
writes, delays, reset, retry or hardware cleanup. Synthetic cases distinguish
a selector that remains zero, one that appears correct immediately then reads
zero, and a bad immediate reply despite a matching later read. Both pipes and
idle restoration are checked before the next entrypoint/activation write.
This change has not executed on the target. Source `280b2b2` passed all 396
Python checks, 226 actual-CLI MES cases in both metadata variants and the
52 transport / 20 completion / 16 submission cases under ASan/UBSan. Its
private Intel userspace diagnostic compiled and linked to native IOKit, but
was not installed or executed against hardware. No kernel was built locally.
See `validation/mes-selector-diagnostic-20261112.json`; these host results
do not establish a target fix or full-stack native CI completion.

Pinned primary-source review is recorded in
`validation/linux-mes-selector-reference.json`. `soc21_grbm_select` uses the
same selector encoding. `gfx_v11_0_cp_gfx_switch_pipe` reads this register
before modifying PIPEID; assuming a write-only selector and removing checks
is therefore unjustified. The RLCG shadow path in `soc15_common.h` is conditional
on SR-IOV VF access and does not establish a missing shadow protocol here.

The existing acknowledged EnableGfxImu argument `1` permits GFXOFF. The same
reviewed MP1 generation offers DisallowGfxOff (`0x1a`, zero argument). This is
a hypothesis to test, not an established explanation. A next test requires
a fresh operator-controlled boot, a new boot-pinned plan and repeated checked
PSP/firmware/power prerequisites. It should acknowledge DisallowGfxOff and
perform only selector writes/readbacks before GART or MES reset. Stop at the
first error; restore idle only after successful selection checks. Do not
unconditionally re-allow GFXOFF on partial failure. Such a test neither
proves causality nor submits GPU work. No power-control message or selector
write was sent during the original stopped boot's follow-up investigation.

## Separate fresh-boot selector probe, 2026-11-12

On the next operator-controlled boot, startup acceptance and the separately
checked PSP/TOC/TMR, seventeen firmware loads, RLC autoload and GFX power
prerequisites passed again. The boot-pinned private selector probe then
received a successful DisallowGfxOff (`0x1a`, argument zero) acknowledgement.
CP/RLC readiness and idle selection were observed before the first selector
write. Expected `0x0c`, the installed CLI reported an immediate readback of zero
and a second read of zero. The later offline audit below qualifies the unchecked
`wreg` reply count in this installed binary. The probe stopped there: it never
selected pipe 1, restored idle, initialized GART, reset/activated MES or
created/submitted a queue. No
further GPU register writes or same-boot retries followed. See
`validation/mes-selector-target-20261112.json`.

An acknowledged inhibition message alone did not fix selection. This does not
independently verify the hardware exited GFXOFF or eliminate all power/access
conditions. The mismatch was observed before any GART/MES reset in this boot;
the probe does not establish a complete hardware reset across reboot. Root
cause and write-only semantics remain unestablished, so the readback checks
stay intact.

At that stop, the remaining GC segment bases originated from the reference
machine, without independently captured target IP discovery. No PhxProbe
service or already published discovery data was found, and the default
discovery tail lies outside the direct VRAM aperture. Do not scan guessed MMIO
bases or initialize another
stage to work around this missing evidence.

A private userspace capture prototype is prepared for a **fresh pristine boot
before any PSP/firmware/power initialization**. It uses the existing checked
transport in one connection and gates on configured-only kernel metadata,
firmware initialization status and matching memory size. The bounded memory
read changes only MM_INDEX/MM_INDEX_HI address selectors; it is not literally
zero-register-write diagnosis. It never writes MM_DATA or any power, GART,
MES, queue or display register. It accepts no arbitrary memory address, uses
no guessed fallback, stops on the first error and retains a private exclusive
partial file. Binary-envelope validation is not IP-table validation or a
hardware-ownership proof. The initialized boot is rejected. Native
compilation and 58 ASan/UBSan fault cases passed before the target capture below.
Source facts and prototype hashes are in
`validation/linux-discovery-window-reference.json`. No kext installation,
kernel build, public diagnostic binary or raw discovery dump is added.

## Target discovery capture, 2026-11-13

A fresh operator-controlled boot passed candidate identity, exact profile,
geometry, installed-stack hashes and startup guards. The private capture ran
once before any PSP/firmware/power initialization. Its configured-only snapshot,
firmware-ready and memory-size gates passed. The bounded memory-window read
completed with a private 10 KiB output; only MM_INDEX/MM_INDEX_HI address
selectors were written. No VRAM data, power, GART, MES, queue or display writes
were made. No further GPU register writes or initialization had followed at
that capture-only checkpoint; the subsequent stages are recorded below.

Offline validation accepted binary version 1.1, a 1,212-byte declared envelope,
all three present table checksums, and an IP discovery version 3 table with
32-bit bases, one die and 39 entries. A separate private validator checked
table overlap/bounds, die/entry/base-array bounds, duplicate instances and exact
entry consumption. Its 31 offline cases passed, including malformed structures
and an independent 64-bit v4 fixture. The repository's existing Python parser
independently produced matching versions and bases for all 39 target entries.
These offline tests do not expand the target capture's supported envelope.

All three target GC bases match the current reference array; both direct SEG
macros match as well. All three MMHUB bases and both OSSSYS bases also match,
with zero-only unused reference-array slots. This supplies the previously
missing target mapping comparison; it does not establish selector accessibility,
actual GFXOFF exit, correct power/clock sequencing or a complete reset across
reboot. Do not change segment bases or remove readback checks on this evidence.

The capture-only stage is complete. Review a bounded power/access observation
plan offline before any further target initialization or register writes; do
not repeat discovery or earlier initialization merely because a new session is
opened. Startup/display protections remain active and the desktop remains on
IONDRVFramebuffer. Acceleration and EDID dimensions remain unresolved. The
sanitized evidence is `validation/ip-discovery-target-20261113.json`; raw data,
addresses, layouts, EFI and firmware remain private. No kext or installed
helper was changed.

## Same-boot staged power and VMID observations, 2026-11-13

After discovery, a separately reviewed private plan observed the existing
checked PSP/firmware/IMU stages without GART or MES. Before initialization, a
standalone zero-write observer read thirteen fixed GC registers, all zero.
A second observer added PSP-initialization and memory-size positive controls,
validated explicit configured/TMR-ready metadata, and required unchanged
bootstrap metadata around every capture. Both positive controls passed at all
four stages:

| Completed stage | Nonzero GC fields of 13 | CP/RLC readiness observed |
| --- | ---: | --- |
| Configured-only baseline | 0 | No |
| Checked PSP/TOC/TMR | 0 | No |
| Seventeen firmware loads and RLC autoload | 1 (IMU scratch) | No |
| Acknowledged EnableGfxImu | 9 | Yes |

After IMU, the named RLC GFX power, clock and pipeline-power status bits were
asserted, RLC was enabled and boot completion was observed. GC reads therefore
do not remain globally zero after this initialization. These observations do
not prove complete GFXOFF exit or eliminate every power/access condition.

The first access-controller attempt stopped after a successful read-only
snapshot because it incorrectly rejected the observer's normal layout message
on stderr. No SMU or selector command was reached. Its sources, logs and
terminal state were retained. A distinct plan pinned that completed capture
and absence of GPU writes, then used a corrected exact diagnostic comparison;
unexpected output and nonzero exits still fail. This was a software validation
recovery, not a retry after a GPU failure.

The subsequent single DisallowGfxOff request was acknowledged. All fifteen
fixed register values were identical before and after it, with nine nonzero
GC fields and the readiness/power checks retained. This is still not an
independent hardware GFXOFF-exit measurement.

The separately invoked VMID-only probe first rechecked positive controls,
readiness, named power flags and idle selection. It wrote VMID 1 with MEID,
PIPEID and QUEUEID zero (encoded selection `0x10`). The installed CLI reported
zero for the immediate readback and subsequent read. Its `wreg` reply count was
not independently checked, as detailed in the later offline audit below. It
stopped on this first selection, without an idle-restoration write or a
later-stage command. The
failure is thus also observed for a value other than the earlier ME3 selection;
it does not establish that every field or every GC write fails. Do not assume
write-only semantics, change the independently matched bases, or remove guards.

The standalone and phased observers passed 90 and 205 ASan/UBSan cases
respectively and compiled as private Intel IOKit userspace programs. The
four-stage controller passed 16 mocked state/failure cases; the corrected access
controller passed 89 mocked state, output and failure cases. These tests do not
execute the real GPU. The installed CLI used for the SMU/selector calls does not
report its service-close result; its checked transport/readback observations
do not establish exclusive ownership or a complete hardware-state proof.

The boot used for that selector diagnostic was initialized and terminal for
further GPU writes. A private
stop record also blocks the parent phase workflow. Startup acceptance and
installed-stack hashes were checked before the access test; those hashes,
startup guards, candidate/profile/geometry and IONDRVFramebuffer were rechecked
after the stop.
There was no GART, MES reset/activation, queue, shader, adoption, claim or display
takeover on this boot, and no kext, installed helper or EFI replacement. Private
session manifests and Chinese next-step/rollback notes are saved. Continue
offline source analysis before preparing another bounded manual-boot test.
Acceleration and EDID dimensions remain unresolved. Sanitized evidence is
`validation/gc-power-selector-target-20261113.json`; raw captures and identities
remain private.

## Offline access-path audit and next observation template, 2026-11-13

An offline inspection checked the accepted private candidate artifact against
its prior binary hash and running private kernel identity. The five relevant
method bodies match the deployed source revision. The identified `writeReg`
machine code bounds-checks the dword offset, stores the caller's 32-bit value,
executes `mfence`, loads the same address and forwards the result. Eight
instruction-sequence mutations were rejected alongside the accepted sequence.
This does not prove the whole dispatch path, physical mapping/cache attributes
or hardware acceptance. The current EFI binary was unavailable at the recorded
path; it was not mounted or independently rehashed for this review.

Inspection of the installed CLI exposed a diagnostic limitation: its `wreg`
branch requests one output scalar but does not compare the returned count
before printing the output buffer. Thus the prior printed zero words do not
independently establish a complete reply shape. A short reply on the target
has **not** been observed or established as the cause. The earlier stop remains
binding; this finding is not permission for a same-boot retry.

A private userspace CLI was compiled from exact repository source `853d43c`,
which already checks IOKit status/counts and kernel ABI. Thirty-six actual-CLI
synthetic shape/ABI cases and sixty existing firmware/control cases passed
under ASan/UBSan; four native CommonCrypto file-only cases passed without
opening IOKit. Successful zero data and malformed reply sizes are tested
separately. No installed helper is replaced. Its service-close return remains
unreported; this limitation is not removed by the other transport checks.

The next private template adds only three read-only state fields to the
fifteen-field observer: GRBM soft reset, CP ME halt control and CP soft reset
control. Their offsets and individual segment indices were checked against the
pinned primary source. The eighteen-read observer passed 229 ASan/UBSan cases
and native Intel IOKit compilation; the stage controller passed sixteen mocked
cases and the boot preparer thirteen synthetic cases. The real stopped boot
was rejected before any target-plan creation or GPU command.

After a new manual boot, preparation must bind a new plan to that boot and
recheck startup acceptance and input hashes. Only future private-session
helpers use the checked CLI, with reviewed whole-file SHA-256 arguments added
to staging/loading calls. The existing PSP/firmware/IMU order is retained;
every stage gets a fixed observation. There is no selector, DisallowGfxOff,
GART, MES, queue, shader, adoption, claim, display or reset-write stage. Reset
and halt states are observations, not an instruction to clear bits or a
diagnosis by themselves. Neither new private native tool has executed against
the target GPU. Source, binary inspection limits and preparation evidence are in
`validation/gc-access-audit-20261113.json`. Acceleration and EDID dimensions
remain unresolved.

## Subsequent fresh-boot compute acceptance, 2026-11-13

A later user-authorized restoration of the existing startup switch and manual
boot took the legacy initialization path through queue adoption and claim.
The older installed accelerator published NMXAccel, and a separate private
Metal smoke passed all six real compute cases on the PCI-verified 780M. This
is new, bounded execution evidence for that running mixed stack, not a replay
of the stopped selector experiment or execution of the checked reset-observation
template. It does not explain the earlier zero readbacks, remove CLI transport
limits, prove memory ownership or accept the standalone guarded MES workflow.

At that checkpoint desktop takeover was pending a separate manual boot. See
`LEGACY-BOOT.md` and `validation/metal-postboot-target-20261113.json` for the
identity checks, six compute results and remaining display/provenance limits.

The subsequent display boot failed and the existing startup monitor automatically
returned to IONDRVFramebuffer after three WindowServer reports. NMXAccel remains
present, but M2 and framebuffer arming have been cleared. Two reports identify
RADV command-stream failure cleanup; another process logged
`VK_ERROR_DEVICE_LOST` before a CoreDisplay abort. A source-only cleanup-order
patch has bounded CPU tests, not native-runtime or GPU acceptance. Do not rearm
display takeover, replay initialization or treat this as acceptance of the
guarded MES workflow. See `validation/display-postboot-target-20261113.json`.

The read-only follow-up found that the pinned RADV queue layer converts
different submission failures into device loss; the exact original native
refusal remains unknown. A metadata-only query on the fallback boot reports
256 MiB ordinary and 512 MiB device-local heaps, consistent with the reviewed
APU split, not evidence of global VRAM exhaustion. Keep the fallback state;
see `DISPLAY-FAILURE-20261113.md` and
`validation/display-followup-target-20261113.json` for source/provenance limits.

A subsequent source-only build-35 diagnostic records the first non-success
native submit IOReturn per client, without changing dispatch results, the
submission guards or reclamation methods. It has CPU dispatcher tests and
has not been installed or accepted on the target. See
`NATIVE-SUBMIT-DIAGNOSTIC.md`; keep the current fallback state.
