# Terminal desktop queue-selector preflight

Status, 2026-11-14: **one separately authorized native preflight ran and stopped
at the first KIQ selection: requested `0x0000000d`, write readback and subsequent
readback both zero; exit 75**. Firmware/power returned zero. The corrected
system-domain watchdog became ready, dismissed after the finite diagnostic
and was removed. No GART/MES/queue initialization or desktop takeover followed.
See [the target result](#system-domain-target-result).
An additional [VMID-only control candidate](DESKTOP-VMID-PREFLIGHT.md) now
exists in source for a separate future experiment. It does not replace these
queue checks or change their order and has not been target-executed.
The [original build-39 desktop attempt](
DESKTOP-DEPLOYMENT-ADMISSION.md#observed-reboot-result-and-recovery) stopped at
queue-selection readback before GART/MES initialization. Its one-attempt
authorization is consumed. The installed binary did not log which of the four
selections failed or the immediate/later readback values. A later pre-GPU
admission was consumed at watchdog readiness; the following distinct target
experiment supplied the KIQ readbacks above. It does not retroactively identify
the original failed queue or establish the physical cause.

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

At the source milestone, the actual CLI and provider methods passed **25 CPU test methods** under
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

## Later target admission and launchd correction

A later owner continuation authorized one separately scoped terminal preflight.
The original desktop request and all 188 consumed receipt hashes were preserved.
Admission observed macOS 26.7.2, build 25G332, the same recovery boot and build-39
provider. PhxAccel and its accelerator service were absent while the firmware
framebuffer was present. This differs from the original desktop attempt; it
must not be used to attribute the earlier selector failure to the accelerator.

An independent copy of the validated native helper was ad-hoc signed and passed
strict signature verification. The unsigned validated bytes were preserved.
All 43 experiment input pins, ten recovery pins and the complete trusted
interpreter tree passed verification. Neither signature verification nor this
private staging is an OS driver approval or driver/startup deployment.

The fresh max-one request was durably consumed. `launchctl submit` returned
success, but no bound watchdog-ready record appeared within five seconds. The
runner refused before either firmware/power or `desktop-preflight`: **zero new
IOKit service opens, snapshots, reservations, selector writes or initialization
commands**. The refusal completed without a recovery/reboot request. The scope
was not reset or retried.

Readback found the submitted job in the graphical bootstrap domain despite
effective UID zero. It was repeatedly failing to spawn with `EX_CONFIG`, with
no child output or ready record. System-domain lookup alone had missed it.
The inherited domain is established; the precise underlying spawn permission
failure is not. The exact graphical-domain job was removed and its absence
verified. These are launcher observations, not GPU failure evidence.

A separate private launcher candidate now writes a scope-local native plist
and uses `launchctl bootstrap system` with `UserName=root`, `RunAtLoad=true`
and `KeepAlive=false`. It retains bootstrap stdout, stderr and status, and
requires a request-bound ready receipt reporting effective UID zero. It also
gives recovery/deadline checks priority over late completion records and checks
the work budget and watchdog again after input hashing. It is not installed as
a persistent LaunchDaemon or startup caller; the consumed frozen delivery was
not modified.

Twenty-five file/mock tests passed under the trusted interpreter, including
five system-launch contracts, deadline races, input drift, duplicate refusal,
finite failure, timeout and no-later-command behavior. A separate file-only
host probe used that candidate's actual launch function. Its child reported
effective UID zero and launchd as parent, survived the submitting process,
ran exactly once, and exited zero after an explicit file release. The exact
system job was then removed and absence verified. The probe had no GPU or
reboot command. This validates the corrected launch path only; **the corrected
candidate has not run a GPU preflight or proved deadline reboot recovery on
hardware**.

Final metadata admission retained the same boot/provider identity, firmware
framebuffer, off marker and absent display arming; all original receipt hashes
still matched. No driver, installed startup, EFI, security setting or proxy was
changed. See the [sanitized admission record](
validation/desktop-selector-preflight-admission-20261114.json).

Any further target experiment must use a fresh independently reviewed max-one
request and scope, with the system-domain correction and immutable input pins.
Do not replay either consumed scope or continue to same-boot initialization.
For the unused candidate, rollback is simply to retain it as private evidence
and not select it; no installed component needs restoration. Remove only the
exact experiment-owned launchd label in its verified domain if cleanup is
needed; never remove unrelated jobs or use a broad process kill.

## System-domain target result

After a new owner continuation, a distinct max-one request selected the
validated system-domain launcher with a new label. Its execution logic and the
signed native helper were unchanged; only the launcher label was rebound.
Admission checked 44 input pins, ten recovery pins, the complete interpreter
tree, all 188 original desktop receipts and all 29 prior preflight-admission
receipts. Both prior scopes remained consumed. The same recovery boot/provider
identity, macOS 26.7.2 build 25G332, build 39, firmware framebuffer, off marker
and absent display arming were retained. PhxAccel was still absent.

The explicit system-domain job reported a request-bound ready receipt with
effective UID zero. Exactly one firmware/power prerequisite command returned
zero and its expected completion marker. Exactly one `desktop-preflight`
then returned 75 with this extracted diagnostic:

| Phase | Queue | ME | Pipe | Queue ID | VMID | Requested | Write readback | Subsequent readback |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| Select | KIQ | 3 | 1 | 0 | 0 | `0x0000000d` | `0x00000000` | `0x00000000` |

No other queue selection, restoration, retry, doorbell/CP setup, GART/MES/queue
initialization, VRAM access, seal, claim or display stage followed. The command
does not reach its success-only checked service close on this failure path;
do not report a successful close or independently observed kernel reservation
abandonment. No live GPU request tracing was installed. Source control flow
and the new fake-only regression imply one snapshot, one reservation, one
selector write and three explicit register reads for this path; these counts
are not independent target instrumentation.

The watchdog recorded normal terminal dismissal without requesting reboot.
System-domain readback showed one run and exit zero; the exact job was removed
and absence verified. Final metadata retained the same boot/provider/service
identity, firmware framebuffer, off marker and absent display arming. Both
prior receipt sets still matched. The new target scope is consumed and was
not reset or retried. No driver, installed startup, EFI, security setting or
proxy changed.

Offline rechecking verified all eight cached files against the pinned Linux
selector-source manifest. Existing GC register definitions and the SOC21
field encoding agree with `ME=3, pipe=1` producing `0x0d`; the helper's offset
and base index match those definitions. The executed helper checks transport
status and reply shape, so the older unchecked-CLI scalar-count qualification
does not apply to this recorded failure. A completed firmware/power command
still does not establish every GC initialization prerequisite or successful
GPU execution. The result does not establish a write-only selector, a mapping
or GFXOFF defect, or an accelerator conflict. It observes a selector mismatch
in an accelerator-absent environment; the original accelerator-present attempt
was not a controlled comparison.

A new CPU regression injects this exact dual-zero response for both
`desktop-init` and `desktop-preflight` with reference and relocated layouts.
It asserts exit 75, the exact phase/fields/readbacks, one selector write, three
explicit reads, no later work and no false success. All **26 native CLI/provider
test methods** passed under ASan/UBSan with zero skips, including these four
new cases. The launcher also passed its 25 file/mock methods under the trusted
interpreter. Production helper and kernel source were not changed. The earlier
629-test full-suite result is historical and was not rerun for this targeted
test/documentation change. See the [sanitized target record](
validation/desktop-selector-preflight-target-20261114.json).

That preflight boot was terminal for GPU work. Preserve the readback guards and
these consumed scopes. Further hardware diagnosis requires a fresh boot and a
separately reviewed, byte-pinned, bounded request with independent recovery;
do not bypass the selector check, repeat firmware/power or continue to
initialization on that boot. Review GC access and initialization prerequisites
offline before selecting another experiment. No recovery rollback was needed
for this finite failure; no persistent launcher or installed component was
changed. Revert only the new fake-test case as a normal commit if necessary,
retaining the hardware evidence and existing guards.

The subsequent [fixed GC observer](
GC-STATE-OBSERVATION.md#fresh-boot-target-observations) completed baseline and
post-power observations on a separately admitted fresh boot after an explicit
owner-requested reboot. READ_TIMEOUT changed from zero to `0x30`, with changed
CP/MES halt fields. No selector write was performed, so this does not reproduce
or explain the earlier failed preflight. Its distinct request is now consumed
and that new boot is also terminal; no same-boot continuation, selector bypass
or automatic retry was added.
