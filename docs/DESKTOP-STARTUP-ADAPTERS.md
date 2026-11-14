# Checked desktop startup and retained display ordering

Status, 2026-11-14: **build-39 candidate installed; original single-request reboot
diagnostic armed and scheduled; hardware result pending**. Build 37 remains
loaded on the current boot.
`tools/desktop_startup.py` supplies concrete commands for the [coordinator](
ALLOCATION-STARTUP-COORDINATOR.md) and [build-39 handoff](DESKTOP-NATIVE-HANDOFF.md).
There is no default packet, installer, arming command or automatic next attempt.
Source tests do not consume the outstanding owner's desktop request.

## Sequence and delivery contract

A private root-owned delivery must pin the interpreter, launcher, modules,
native helpers, reader, firmware, installed inputs and separate recovery subset.
Commands verify their packet and complete Python runtime. Recovery does not
depend on live GPU-stack pins remaining unchanged. The fixed scope and request
digest must be bound externally to the original authorization; choosing another
scope is not permission to repeat an attempt.

1. `run` durably claims `boot-entry.started` and arms independent recovery before
   boot metadata discovery. Bounded metadata-only waiting permits delayed
   publication; unexpected builds are refused. Both loaded kext images must match.
2. The actual coordinator claims `startup.started` and arms its recovery before
   the metadata guard may dismiss. The new owner retains the original absolute
   240-second deadline. Receipts distinguish this handoff from final dismissal.
3. The actual observer owns one baseline and at most one failure read. Readiness
   follows baseline completion and the first clean report scan. The coordinator
   checks identity, schema, hash and remaining retained capacity.
4. `initialize` checks display history, runs checked `gfx-power-sequence` with
   explicit PSP geometry, checks again, and runs `desktop-init` with explicit
   GART/four-queue geometry. Firmware failure cannot fall through.
5. `claim` requires completed initialization and exact `desktop-claim` success.
   `display` requires claim completion and one NMXAccel, checks reference
   flush/display/copy writes and readbacks, and observes AGDC up after requesting
   its asynchronous worker. Existing allowlist bytes are preserved and must
   already admit the intended desktop in the reviewed delivery.
6. `release` requires completed display setup, an unexpired never-released hold
   and no server request since preparation. It saves reference report and panel
   copy counts, releases, and checks retained release history against the call
   interval and any subsequent server request.
7. `monitor` retains 18 five-second checks: three WindowServer reports in the
   initial 90 seconds request recovery. One/two reports do not replace that
   threshold. The observer's first-report capture is independent. WindowServer
   presence and a currently open panel client are checked afterward. Copy-count
   progress is evidence, not proof of a usable accelerated desktop. This stage
   has 100 seconds, rather than the library's generic 60 seconds.
8. The entry process then remains alive in `watch`: 15-second checks, two
   hyphenated `.ips` reports within five minutes, three recorded reboots within
   an hour. It never creates persistent M2 or rearms NVRAM on success.

Each mutable stage has a durable exclusive claim and separate completion.
Failures propagate. No legacy initializer, output filter, global process kill,
snapshot polling, queue reset or hold rearm is used. Role budgets remain
subordinate to the original absolute watchdog and independent hold timer.

## Retained display history

`PhxDisplayHistory.h` defines a 144-byte version-1 read-only observation.
`debug.phxfb_history` copies it under the existing hold lock. It retains
framebuffer identity and monotonic timestamps/counts for preparation, boot hold,
first release/reason, server requests and successful connections. It contains
no task IDs, pointers or page contents.

Preparation precedes `IOFramebuffer::start`. The actual server override records
requests before delegating, including failures, and success only after the base
method succeeds. Shared/read-only connections are distinct. Hold release is
recorded before `adjustBusy(-1)` can publish the GPU. Timeout, explicit release
and stop retain different reasons. History is never reset; restart, rearm or
failed timer allocation invalidates admission. The hold remains 120 seconds and
AGDC scheduling stays asynchronous. Its recorded deadline conservatively starts
at the hold transition, before scheduling the existing timer. A late read cannot
erase an earlier timeout/request. Current panel presence is read separately:
historical success does not mean a closed client is currently open.

## Runtime and recovery

The live adapter requires **Python 3.13+** in a pinned root-owned runtime.
macOS system Python 3.9 has a per-process monotonic epoch, unsuitable for kernel
history comparisons across exec. The private clock check brackets native
`mach_absolute_time` nanoseconds with the tested Python 3.13 clock. A runtime
manifest verifies its complete file set, ownership, permissions and hashes,
including libpython. Commands use isolated/no-site/no-bytecode execution.
System libraries remain tied to the exact checked OS build.
Command-input pins stream through a 256 MiB cap to cover the actual 17 MiB
interpreter and 139 MiB installed LLVM dependency without a large memory copy;
standalone snapshot-reader and output limits are unchanged.

`disarm` writes the existing kill switch, removes persistent M2 if present,
deletes display arming, forces its existing sync and verifies actual not-found
status. Permission errors are not absence. `recover-display` is independent:
its return cannot gate disarm/reboot. `reboot` has one exclusive dispatch claim
shared across recovery paths. Recovery never waits for the observer, a stage,
termination or collection. Later fallback uses the same independent dispatcher.

This cannot guarantee progress through an uninterruptible kernel, bus,
filesystem or whole-system hang. Dispatch does not prove firmware fallback.
The operator recovery route and exact installed rollback remain necessary.

## Validation and installation boundary

CPU tests execute actual hold/history functions and the server override under
ASan/UBSan. Process tests execute actual adapters, coordinator, observer and both
recovery owners with closed-whitelist fake I/O. They cover success, failed
firmware and blocked display recovery while independent disarm/reboot proceeds.
Other cases cover historical ordering, gates, runtime tampering, non-replay,
crash thresholds and role budgets. Fixtures replace native effects and shorten
waits; they neither emulate a GPU nor establish a desktop.

A fresh complete trusted packet is still required: matching kexts, helpers,
capture/observer/coordinator, interpreter/import closure, startup replacement and
rollback. The installed PhxAccel is a distinct retained image; compilation is
not deployed telemetry. Preserve its entire rollback bundle and update/check
the applicable kernel collection through existing security settings. Do not mix
old capture delivery with this coordinator, replay consumed build-37 operations,
use the unknown installed legacy helper or call Phase A's post-initialization
snapshots a pre-initializer baseline. Source rollback is an ordinary revert.
Private evidence stays ignored; public kext/RADV exceptions and the full-stack
publication block are unchanged.

## Final local checks, 2026-11-14

The final clean isolated committed snapshot passed **623 tests** on Python
3.13.18 in **329.561 seconds**, with zero skips and unchanged tracked inputs.
It includes 30 desktop-adapter and 47 coordinator test methods. Both kexts
and all three helpers compiled, linked and passed x86_64 and strict ad-hoc
signature checks. All 1,232 pinned SDK files matched before and after building.
The [validation record](validation/desktop-startup-adapters-20261114.json)
contains source/binary hashes and scope limits. Earlier rejected development
runs are preserved privately and are not counted as final passing evidence.

A private root-owned Python runtime and complete candidate delivery have been
staged. A fresh full 340-file EFI backup and old PhxAccel backup were verified,
and EFI was unmounted. Read-only native metadata adapters and three
Python/native-clock brackets passed. None of this installs/loads a driver,
arms display takeover, invokes a target snapshot selector or proves a desktop.

The subsequent [deployment-admission record](DESKTOP-DEPLOYMENT-ADMISSION.md)
separately records installation of the matching KDK and the first seven
unsuccessful, rolled-back kernel-collection admissions. At that point the
installed driver remained build 37; normal AuxKC approval had not passed and
the requested desktop diagnostic remained unconsumed. Later readbacks confirmed the owner's Terminal
Accessibility and Screen Recording grants and an allowed PhxAccel policy row,
but the new candidate was not cached at that point. A host reboot invalidated the old
preparation's boot match. After a locked-console interval, desktop capture
recovered following the owner's request to disable automatic display and idle
system sleep. These observations and the newly verified rollback hashes are
recorded there. A separately prepared current-boot delivery then reached an
ordinary Terminal rebuild under the owner's nonprivileged UID and was refused
with `Operation not permitted`. Independent readback verified complete rollback;
the original diagnostic scope remains empty. The fresh delivery did not modify
or replay old boot-bound records. Subsequent direct operation of the PhxAccel
Allow row in Privacy & Security, including owner-authorized password entry,
completed normal GUI authentication and produced a restart-required message.
Readback still found the original accelerator installed and cached. That route
can inform a separate reviewed candidate admission; these observations are not
a successful candidate installation or desktop test. A fifth admission then
ran the fixed rebuild command through normal sudo in that ordinary Terminal.
Password authentication passed and the candidate replacement was detected,
but the OS authentication request still returned `Biometry is not available.`
Independent readback again verified the original accelerator, startup, all 24
caches and complete 340-file live EFI after rollback. Thirteen local
installer/channel CPU cases passed; the original one-diagnostic scope remained
empty. The owner-login context alone has therefore not resolved cache admission.
Two later admissions attached all standard streams directly to native owner
Terminal for manual authentication. The sixth timed out and was independently
rolled back. In the seventh, the owner entered the password directly; sudo
passed, but the subsequent OS authentication again returned the biometric
refusal with status 250. Both installers passed 16 local CPU cases. Complete
rollback was independently verified after each, including all 24 caches and
the 340-file live EFI. All ten production hashes remain unchanged; the original
diagnostic scope remains empty. Neither manual input nor native standard
streams has established a successful AuxKC approval route.

The owner then explicitly selected the upstream `create`/inspect/backup/publish
route after its action-specific `-z` approval skip was explained. The eighth
admission failed on a KDK dependency; the ninth created a collection but omitted
PhxAccel and was refused before publication. Both were independently rolled
back. The tenth explicitly selected all four existing auxiliary identifiers and
checked Boot/System/Aux together: create succeeded, all 416 identifiers matched,
and the exact candidate replaced only PhxAccel while all 415 unrelated cached
records stayed exact. The candidate AuxKC, build-39 EFI driver and next-boot
startup entry were installed. Independent readback at 19:25:23 +08:00 verified
all 37 packet pins, seven recovery pins, unchanged production hashes, original
backups and the entire expected live EFI; EFI was unmounted. Global security
settings were unchanged. This is successful next-boot installation, not normal
`rebuild` authentication or hardware validation. Build 37 is still loaded; no
arming, diagnostic, initialization, reader or reboot was executed, and the
original diagnostic scope remains empty.

The later [single-request reboot admission](DESKTOP-DEPLOYMENT-ADMISSION.md#original-single-request-reboot-admission)
rechecked the full installed packet, trusted runtime and alias trees, complete
EFI and recovery state. It armed one one-shot display flag and scheduled one
identified restart under the original one-attempt authorization; no persistent
M2 flag was created. The original scope was still empty at independent readback.
The entry was not run on the initialized current boot. Reboot and desktop
results remain unobserved in this record; inspect the original scope first on
resumption and never silently repeat the attempt. Ten inert operational tests
passed without GPU I/O. The unchanged 623-test source result remains CPU/source
evidence only; independent recovery cannot cover every kernel or bus hard hang.
