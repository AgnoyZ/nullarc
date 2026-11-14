# Terminal desktop queue-selector preflight

Status, 2026-11-14: **source and CPU validation only; not installed or run on
the GPU**. The [original build-39 desktop attempt](
DESKTOP-DEPLOYMENT-ADMISSION.md#observed-reboot-result-and-recovery) stopped at
queue-selection readback before GART/MES initialization. Its one-attempt
authorization is consumed. The installed binary did not log which of the four
selections failed or the immediate/later readback values. No new hardware
attempt is part of this change, and the physical cause remains unknown.

## Evidence and retained guards

The pinned Linux `soc21_grbm_select` uses the existing PIPEID/MEID/VMID/QUEUEID
encoding. `gfx_v11_0_cp_gfx_switch_pipe` reads the same selector before changing
PIPEID; these sources do not support assuming write-only semantics. Their
cached bytes were rechecked against [the pinned source manifest](
validation/linux-mes-selector-reference.json), including their MIT-style
notices. A fresh download timed out and is not reported as a new downloaded
hash verification. No upstream implementation body is copied by this change.

Earlier [target IP discovery](validation/ip-discovery-target-20261113.json)
matched all three GC bases and both direct segment macros. The earlier
[power/selector observation](validation/gc-power-selector-target-20261113.json)
still failed after an acknowledged DisallowGfxOff request. Its printed zeros
have the later [unchecked scalar-count qualification](
validation/gc-access-audit-20261113.json). Neither a base-address error, a cache
mapping defect, write-only semantics nor a GFXOFF cause is established. The
current helper checks transport status and reply shape. Preserve its readback
and idle checks; do not bypass them or change mapping/power behavior on this
evidence.

## Explicit command and boundary

`mesboot desktop-preflight` takes exactly the same explicit arguments as
`desktop-init`: four GART values followed by KIQ, scheduler, compute and graphics
arena/doorbell pairs. It has no default geometry, shell wrapper, environment
override or startup caller. The existing firmware/power prerequisites remain
external; this command does not perform them.

The command reuses the strict driver/bootstrap/layout checks and selector-117
exclusive reservation, then checks inactive MES and idle selection. It runs
the same four queue selection/idle checks in the existing order:

| Queue | ME | Pipe | Queue ID | VMID |
| --- | ---: | ---: | ---: | ---: |
| KIQ | 3 | 1 | 0 | 0 |
| Scheduler | 3 | 0 | 0 | 0 |
| Compute | 1 | 0 | 0 | 0 |
| Graphics | 0 | 0 | 0 | 0 |

This is a **mutating diagnostic**, not a passive capture. A passing invocation
uses one service connection, one boot-memory snapshot, one reservation, eight
selector write requests (each returning the existing kernel write readback),
fourteen separate register-read requests and one checked service close.
Register reads are limited to the selector, MES control and the two queue
active registers. The command returns before doorbell/CP setup, GART/MES
initialization, VRAM access, queue initialization/submission, seal or claim.

A selection or restore mismatch logs phase, ME/pipe, requested value and both
existing readbacks, then stops with status 75. No later restoration write,
retry or rollback is added. Transport and close failures remain terminal
status 74. Closing an incomplete reservation intentionally abandons it under
the existing provider policy. Even a successful preflight is terminal for
same-boot initialization; it is not an initializer prerequisite or a lease
release API.

## Verification and future experiment

The actual CLI and provider methods pass **25 CPU test methods** under
ASan/UBSan. Four new methods cover reference/relocated success, six injected
selection/restore faults, fourteen argument/layout/transport/state refusals,
and service-close failure. The fake backend asserts the preflight register
allowlist, reserve-only selector-117 operation and absence of VRAM/doorbell
calls. Success also asserts the exact request counts above. A real x86_64
IOKit/CoreFoundation compile/link passed; that binary was not executed or
installed. See [the sanitized validation record](
validation/desktop-selector-preflight-20261114.json) for input hashes and the
complete regression result.

A future target experiment needs a separate explicit one-attempt scope,
byte-pinned helper/runtime/arguments, fresh boot admission, prerequisite and
recovery review, and retained diagnostics. Stop after the first failure or
after a passing preflight; do not continue to initialization on that boot.
Do not modify or replay the consumed desktop scope, install a new startup
caller, arm display takeover, alter EFI/security settings or schedule a reboot
as part of this source milestone. Any firmware/power or recovery operations
must be accounted for separately from the command's bounded requests.

For source rollback, revert the preflight addition as a normal new commit.
Keep the prior error-detail logging and existing selection guards. There is
no installed rollback for this uninstalled source change.
