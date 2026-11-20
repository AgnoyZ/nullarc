# Build34 R1b ring and submission-history wait

R1b starts from the running, hardware-checked R1a kernel at
`568e80b205c10b00cba4f21c6d324d239d725bfd`. This candidate handles exhaustion of
ring space or submission-history slots in `PhxBringup::gpuSubmit`. The default
branch source contains the change. Hardware validation is pending, and the
loaded PhxBringup still matches the accepted R1a executable on macOS 26.7.2
build 25G332. [R1a hardware evidence](validation/build34-wait-boot-20261120.json)

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

The hardware trial needs separate authorization to replace the boot-injected
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
