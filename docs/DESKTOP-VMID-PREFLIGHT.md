# Terminal VMID selector control probe

Status, 2026-11-14: **source/CPU diagnostic candidate only**. No target-linked
helper was executed, installed, signed for delivery or uploaded by this change.
The latest [GC observation experiment](GC-STATE-OBSERVATION.md#fresh-boot-target-observations)
remains consumed and its boot remains terminal for GPU work. This addition
neither fixes desktop takeover nor authorizes a reboot or another target test.
The later [inert delivery preparation](#prepared-single-attempt-experiment)
also passes file/mock validation; no fresh-boot admission or GPU execution has
followed it.

## Why test VMID separately

The earlier [queue preflight](DESKTOP-SELECTOR-PREFLIGHT.md#system-domain-target-result)
stopped at its first selection, ME 3 / pipe 1 / queue 0 / VMID 0: requested
`0x0d`, with both readbacks zero. It did not test another selector field.
The later observation on a different boot measured READ_TIMEOUT `0x30`,
CP/MES halt fields set, and MES pipe reset/active fields clear. Those captures
contain no selector write; they cannot identify the cause of the earlier failure.

Linux commit `7d0a66e4bb9081d75c82ec4957c50034cb0ea449` provides a reason
to separate VMID selection from MES selection:

- `gfx_v11_0_hw_init` calls `gfx_v11_0_constants_init` before RLC/CP resume.
  Its constants stage selects VMIDs with ME, pipe and queue all zero.
- `mes_v11_0_enable(true)` sets MES pipe reset fields before its ME-3
  selections. The local `mes_start` also resets before selecting ME 3,
  while the desktop idle guard selects ME 3 earlier.
- `gfx_v11_0_cp_gfx_enable` controls CP halt fields, but source order alone
  does not prove those fields caused a failed selector readback.
- The constants stage programs READ_TIMEOUT `0xff` before its VMID loop.
  That differs from the later target's nonzero `0x30`; neither value establishes
  the timeout needed for selector access on this target.

The candidate tests only the VMID field with the current timeout/reset/halt
state. It does not move CP/MES initialization earlier, change timeouts, or copy
the Linux constants stage. The five relevant cached primary files and their
AMD MIT-style notices were checked against existing manifest hashes; fresh
downloads of the three C files did not complete. No upstream function bodies,
whole headers or binaries were copied. See the [source/CPU validation record](
validation/desktop-vmid-preflight-20261114.json).

## Fixed command and scope

`mesboot desktop-vmid-preflight` takes the same twelve explicit layout values
as `desktop-preflight`: four GART values and four arena/doorbell pairs. Keeping
that layout contract preserves the existing geometry, environment and exclusive
provider-reservation checks; the command does not initialize those resources.
Firmware/power prerequisites and independent recovery remain external.

After the existing inactive-MES and idle-selector checks, the command:

1. Writes `GRBM_GFX_CNTL` with only VMID 1 selected (`0x10`). Records and
   checks both the kernel's write readback and a separate readback.
2. Only if both match, writes the idle selection (`0`). Records and checks
   both readbacks again.
3. Only if all checks pass, closes the service with status checking and emits
   a distinct `desktop VMID preflight:` completion marker.

A passing path has one service open, one ABI handshake, one bootstrap-memory
snapshot, one selector-117 reservation, **two fixed selector-write requests,
four separate register reads and one checked close**. Reads are restricted to
`CP_MES_CNTL` and `GRBM_GFX_CNTL`; writes are restricted to `GRBM_GFX_CNTL`
with values `0x10`, then `0`. Counts come from source and the fake backend,
not live GPU tracing.

This is a mutating terminal diagnostic. A readback mismatch exits 75. A
transport/status/shape or service-close failure exits 74. After failure there
is no later selector write, restoration, retry or initialization. Success uses
the existing close/abandonment policy and still does not permit same-boot
initialization. A failure before checked close does not independently prove
that reservation abandonment was observed on hardware.

There is no banked-register access, queue-active probe, CP/MES reset, timeout
or halt write, GART setup, VRAM access, doorbell, seal, claim or display step.
The existing `desktop-init`, `desktop-preflight` and startup adapters retain
their original order and guards; none calls this diagnostic automatically.

## Interpretation and future boundary

A VMID mismatch would show that a non-MES selector field also failed under
that experiment's conditions. Matching VMID readbacks would establish only
that this VMID transition was read back correctly. It would not prove VMID
isolation, bank routing, MES-specific failure, queue readiness, GPU execution
or a desktop fix. Comparing a future passing VMID probe with an earlier
failing KIQ probe on another boot cannot by itself isolate a physical cause.

Any target use needs another verified fresh boot, a distinct reviewed max-one
request, pinned native inputs/arguments and prerequisite/recovery review with
an independently ready watchdog. Do not replay consumed scopes, run this on
the current terminal boot, chain it into initialization, alter EFI/security
settings or schedule a reboot as part of this source addition. Stop after its
first failure or success. Private trace output remains ignored and unpublished.

## Validation and rollback

The actual native CLI is exercised through fake IOKit under ASan/UBSan.
New cases check reference/relocated success, immediate-only and subsequent-only
mismatches, all-ones and dual-zero observations, every read/write transport
position, inherited admission refusals and close failure. The fake enforces
the exact write values, register allowlist, reserve-only operation and absence
of VRAM/doorbells. Existing desktop, collector, analyzer, startup, layout and
native-include contracts are rerun; current counts are in the validation record.

A real x86_64 IOKit/CoreFoundation compile/link is separate from execution.
The first warnings-as-errors compile rejected the existing legacy unused `val`
variable; the subsequent compile excludes `-Wunused-variable` and passes with
the other warnings treated as errors. That binary remains local and unexecuted.

For source rollback, revert only this diagnostic addition in a normal new
commit. No installed component was changed. Keep prior target receipts and
all consumed requests intact.

## Prepared single-attempt experiment

A separate private execution candidate now fixes the order to one configured
observer, the unchanged firmware/power command, one TMR-ready observer, then
one `desktop-vmid-preflight`. It preserves the previously executed observer's
bytes and uses a separately signed copy of the new VMID helper. Ten native
source dependencies match the source candidate. Signature checking is for this
private tool copy and does not establish OS driver approval.

Before the VMID command, the candidate requires the observer's always-on
controls, matching memory-size controls, CP_STAT zero, RLC bootload completion,
inactive MES and idle selection. It validates the exact VMID trace sequence
and distinguishes matching numeric readbacks from checked command completion.
Every finite failure ends the experiment; unknown results or a timeout request
independent recovery. No path continues into queue initialization or display.

The proposed work budget is 120 seconds, with a separately ready system-domain
root watchdog at 150 seconds. Fresh admission would bind 55 input pins and
14 recovery pins, a distinct max-one request and at most one emergency reboot.
These are planned delivery counts, not a completed fresh admission or a
demonstration of hardware deadline recovery. An ordinary reboot to obtain
the required fresh boot is a separate proposed action and has not been scheduled.

The current boot's stable session identifier still matches the completed GC
experiment. An actual administrator-context admission invocation refused with
exit 78, `fresh-boot-required`, before creating a delivery, request, claim,
watchdog or native process. Independent file readback verified those absences
and all four historical receipt sets (188, 29, 97 and 187 files). Forty-nine
existing input pins, twelve existing recovery pins and the complete trusted
Python runtime closure were verified without GPU commands.

Eighty-eight unique CPU methods pass: 35 private runner methods, seven admission/
launcher methods, 31 native CLI/provider methods, seven collector methods and
eight analyzer methods. The 42 private file/mock methods also pass under the
trusted administrator interpreter. The native CLI and collector use fake
IOKit with ASan/UBSan. The earlier 91-method source result is historical and
is not added to this count; the full suite was not rerun.

The preparation remains inert. No new owner-authorization record, live target
scope, installed component, launchd job, GPU call or reboot request was created.
Fresh-boot admission and execution remain pending a separate owner instruction.
See the [sanitized preparation record](
validation/desktop-vmid-preparation-20261114.json). Rollback is to leave this
private candidate unselected and preserve all prior consumed scopes.
