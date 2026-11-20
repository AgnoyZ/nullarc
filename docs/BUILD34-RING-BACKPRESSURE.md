# Build34 R1b ring and submission-history wait

R1b starts from the running, hardware-checked R1a kernel at
`568e80b205c10b00cba4f21c6d324d239d725bfd`. This candidate handles exhaustion of
ring space or submission-history slots in `PhxBringup::gpuSubmit`. The default
branch source contains the change. The first R1b boot loaded the candidate,
but startup stopped at framebuffer admission before the pressure test.
The EFI and startup jobs were restored to R1a, and the later owner-authorized
recovery boot restored the R1a accelerated desktop. Its later readback records
one surface timeout; R1b remains unaccepted.
[R1a recovery and finite automatic-recovery preparation](BUILD34-STARTUP-RECOVERY.md)
[R1a hardware evidence](validation/build34-wait-boot-20261120.json)

When a queue runs out of space, the old path polls every 50 µs while holding
`gpuLock`. This also prevents submissions to the other queue and blocks other
operations needing the same lock. The candidate releases `gpuLock` and sleeps
for 1 ms between retries. Each retry acquires the lock and selects the current
queue, checks its geometry and context, reads the fence, retires completed
entries and checks both capacity limits. This lets another submitter use any
available space in the meantime. The successful capacity check, VM binding and
publication execute in a single lock acquisition. `externalMethod` retains the
submitting client's lock for `doSubmit`, including the wait, so a concurrent
method on that connection cannot unmap its IB or free its BO.

The two-second pressure budget uses elapsed monotonic time, including fence
reads, scheduling delay and lock reacquisition. A retry at or after the
budget returns `kIOReturnBusy` even if it observes newly freed space. It can
retire entries for actual completions, but it makes no new ring write, history
append, sequence allocation or doorbell write. The first check can submit
immediately if there is space. A wakeup or lock acquisition can still take
the call past two seconds. The 1 ms polling interval trades some wakeup latency
under saturation for less CPU spinning. Its effect on frame times needs
measurement. `vmBind` retains its own separate locked wait when hardware VMIDs
are exhausted. The client lock also continues to serialize operations on the
same connection. The scope covers the boot-injected AMD driver during normal
operation.

The production-method regression passes 11 cases under ASan/UBSan. It covers
GFX and compute packets and fences, independent ring and history pressure,
another submission using the freed slot, preferred-queue adoption, changed
geometry, a missing context or queue, and elapsed expiry including delayed
wakeups and clock wrap. The two fast paths also pass on frozen R1a. The nine
pressure cases on R1a fail on its first locked delay. `make test` and the
historical R1a source and artifact unit suites pass. The optional firmware
fixtures were absent. The historical R1a admission rejects the new source as
expected. [Regression fixture](../tests/test_build34_ring_backpressure.cpp)

The separate offline build gates the exact R1a and R1b source bytes and
restricts the delta to the admission part of `gpuSubmit` before VM binding.
The native x86_64 candidate compiles with the pinned MacKernelSDK and passes
strict signature verification. The three existing compiler warnings and all
375 imports match R1a. The matching local KDK/collection lookup resolves the
imports. The Radeon 780M-only bundle differs from the accepted R1a bundle
only in its executable. Native output and full validation logs are private.
[Offline build recipe](../tools/build34_ring_backpressure.py)

The hardware trial needed separate authorization to replace the boot-injected
executable, restart once and run a finite test. Preserve the exact R1a
executable and startup jobs for rollback. Confirm new-boot image identity,
bounded desktop admission and unchanged accelerator, plugin, cache and ACPI.
Use a bounded compute workload to create ring pressure, then measure whether
GFX submissions advance while the compute caller is in the space wait. Record
actual pressure-path evidence along with full-arena IB verification, completion
and the survival of WindowServer. A workload that never exercises the space
wait leaves R1b unverified. Keep the 45/150/300-second startup limits, daily
PR28 configuration and existing monitor policy. On failure restore the exact
R1a disk and job state under the new test scope and report the loaded state
separately. R2–R6 follow successful hardware validation of R1b.

## Authorized pressure trial preparation

The owner authorized one isolated installation, ordinary restart and bounded
pressure test on November 20. The signed native fixture and evidence parser
passed host checks. The existing R1a executable and both startup jobs were
backed up in a separate sealed scope; an inactive atomic rename and rollback
on the target EFI preserved its complete manifest. No Weather work or change
to PhxAccel, the plugin, kernel collections or ACPI is part of this trial.

The pressure fixture uses separate compute and GFX clients. Up to four bursts
submit four 64-IB compute frames per burst. Each outer frame consumes 272
dwords, so a 1024-dword compute ring with the existing 16-dword reserve can
hold only three of them until a fence retires work. The fixture submits a
bounded number of GFX NOP frames concurrently, confirming their exact
queue's fence independently of the global retirement watermark. Every burst
checks the entire 16 KiB arena of both clients, including command and guard
bytes. The fixture drains submitted work and closes both clients on success.
If retirement is uncertain, recovery retains their allocations.

The finite trace matches the signed candidate's sleep callsite and the
probe process, and pairs entry with the return from the kernel delay. It
must show a GFX submission **and** its fence completion inside the same
compute queue-space sleep. Elapsed time in `SUBMIT` alone is not evidence.
The DTrace script compiled and completed an empty dry run on the current OS;
this verifies the trace setup, not queue pressure. The proof is limited to
this bounded run even if it passes. It does not measure FPS or establish
long-term stability.

## November 20 startup failure and R1a disk recovery

The single authorized restart resulted in the 15:25:39 Asia/Shanghai boot on
macOS 26.7.2 build 25G332. The restart command's 15-second wait timed out;
the actual boot and loaded candidate were independently verified, and the
request was not repeated. The owner reported that the machine got stuck
during startup. The OS later responded to read-only checks with a login
session and WindowServer, but physical display recovery was not verified.

The startup controller passed guardian identity and installed-state checks,
then rejected framebuffer admission before invoking the protected startup
shell. The early boot log records that `PhxAMDFB` found the one-use
`phxfb-boot` flag absent and left the firmware framebuffer in place. The flag
had been visible before the restart request; why it was absent during boot
is unverified. Later live readback found one `IONDRVFramebuffer`, no
`PhxAMDFB` or `NMXAccel`, and no loaded PhxAccel. The observer stopped before
creating its probe intent. This trial provides no evidence about compute
queue pressure, GFX progress during a wait, or R1b's performance or stability.

The recovery summary recorded a worker-identity error when checking which
processes to stop. An independent read-only check nevertheless matched all
357 EFI files to the accepted R1a manifest, verified the executable's
signature and matched both startup job files to their sealed R1a copies. The
complete cache metadata, original loaded ACPI and OS security also matched
the accepted expectations. The
observer job file is gone; no R1b worker, retained probe or pending power
process was found. Recovery requested no restart. These are disk and process
checks; they do not replace the R1b kernel already loaded in memory or turn
hardware acceleration back on in this boot.

For a recovery boot, first verify the exact R1a disk and jobs, explicitly
arm and commit the existing one-use framebuffer flag under fresh owner
authorization, read it back before requesting power, and use one ordinary
restart into R1a only. Require current-boot
accelerated desktop receipts before considering a new isolated R1b trial. Do
not replay the consumed observer or probe, skip the framebuffer gate or
start R2–R6. Daily PR28 configuration and the disabled resident monitor were
verified unchanged. See the
[sanitized failure and recovery record](validation/build34-r1b-startup-failure-20261120.json).
