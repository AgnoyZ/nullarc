# Build34 bounded startup recovery

Latest November 20 clarification also authorizes the previously tested ACPI
optimization alongside staged VBL, without waiting for a separate VBL boot.
The [combined adapter and exact recovery](BUILD34-ACPI-RESTORATION-20261120.md)
now supersede the VBL-only staged jobs after independent installed-state
readback. Both restored treatments still await loading at the next boot;
preserve all old scopes.

Later November 20 update: the owner's renewed VBL/ACPI restoration request has
superseded this R1a-only scope's staged jobs. Its exact unloaded watcher file
was retired while installing a new [VBL-compatible finite safeguard](BUILD34-VBL-RESTORATION-20261120.md).
This scope's historical records remain intact; do not replay its preparation
or installation. The new VBL image is on disk only and no new reboot occurred.

On November 20, 2026 the owner authorized one R1a recovery restart and added
automatic recovery for later startup tests. The recovery restart completed
at 16:27:36 Asia/Shanghai on macOS 26.7.2 build 25G332. It loaded the accepted
R1a kernel from `568e80b205c10b00cba4f21c6d324d239d725bfd`, with the unchanged
accelerator/plugin, and passed fresh bounded startup, accelerated desktop and
supervision-ended receipts. Full EFI/cache metadata, original loaded ACPI,
signatures and security checks passed. The existing panel flag was armed,
force-committed and read back through NVRAM and IODeviceTree before the sole
restart request; successful startup rearmed it for the next boot.

The later independent readback found one surface GPU timeout. The other three
error counters were zero. A second finite sample found no further increase,
the same WindowServer, VBL progress and nonzero GPU-copy completions; there
were no new matching diagnostic reports. This confirms the R1a desktop is
running again, but does not pass strict zero-error validation, establish visual
or long-term stability, or permit moving to R1b pressure testing or R2–R6.

## One startup scope, one recovery restart

The [journal helper](../tools/build34_startup_recovery.py) binds one prepared
scope to one new boot. The [host adapter](../tools/build34_startup_host.py)
uses the accepted R1a startup implementation, initialization shell, full-file
checks and unchanged 45/150/300-second admission limits. It adds a separate
finite launchd watcher. The current adapter admits only the existing R1a
runtime; it does not install a candidate kernel or enable a GPU probe.

On an explicit startup failure, or missing completion within 300 seconds of
watcher entry, the watcher takes one durable rollback decision shared by the
startup and guardian failure paths. Before any recovery restart it must:

1. Stop only exact current-boot startup worker groups and confirm retirement.
   CLT's Python launcher and its framework/Python.app executable names are
   recognized, while root identity, process group and all script arguments
   still have to match. An unknown process or retained GPU probe stops recovery.
2. Verify the complete accepted R1a EFI, restore only the two pinned R1a job
   files, remove its own exact watcher job and clear only an exact empty
   pending marker. The accepted kernel, plugin, cache and ACPI are unchanged.
3. Independently re-read the accepted disk/job/runtime files, complete cache
   loading metadata, original ACPI and security before allowing power.
4. Arm and force-commit the existing one-use panel flag, check both NVRAM and
   IODeviceTree and rule out an existing power request. Persist a one-request
   restart intent before dispatch. An exception or uncertain power result
   cannot authorize a retry.

Successful startup instead records acceptance, restores the ordinary R1a
startup job files and removes the finite watcher. Post-startup stalls cannot
reuse this scope to request recovery. The owner-disabled resident monitors
remain disabled. Daily PR28 waiting stays at 250 ms, with WindowServer excluded.
The original frozen controllers and their prior failed/consumed records are
not edited or replayed.

This is a one-boot safeguard, rather than permission to retry experiments
automatically. Each later candidate test needs a new exact-image/recovery
scope with this policy bound to its own files and boot. This R1a-only adapter
must not be relabeled as a validated R1b or build41/build42 installer.

## Validation and limits

Fourteen journal tests cover explicit failure, a missing startup receipt,
concurrent failure reports, success closure, wrong boots, unknown workers,
failed disk/panel readback, symlinks and uncertain restart results. Ten host
tests include an actual idle CLT Python child across its exec transition,
strict process matching, refusal before any unknown job overwrite, no
termination of a retained GPU probe, successful watcher retirement and
preservation of a replaced watcher job. All power callbacks in these CPU
tests are inert. The default unit suite includes both test files.

A fresh root-owned R1a scope was prepared and sealed after actual
runtime/EFI/cache/ACPI checks. On November 20, its two startup job files and
finite watcher job file were installed for the next boot. Separate independent
readback passed the exact sealed files and permissions, full 357-file EFI,
complete 416-record/29-codeless cache metadata, original ACPI/security and
unchanged R1a accelerated desktop. The watcher remains unloaded in the current
boot; no startup job was bootstrapped, no new GPU probe was submitted and no
additional restart was requested. The one-use trial and recovery-restart
journals remain unconsumed.

The same WindowServer survived the installation/readback observation, VBL
advanced, and the existing surface-timeout count stayed at one; the other
three checked error counters stayed zero and no new matching report appeared.
This is installed-state verification, not strict zero-error acceptance or a
hardware validation of automatic recovery. Neither a successful nor an induced
failed boot has exercised the new watcher. The earlier ordinary recovery
restart authorization is consumed; installation does not grant another test
restart. See the [sanitized installation record](validation/build34-startup-recovery-installation-20261120.json).

The watcher needs a functioning kernel and launchd. It cannot execute before
launchd, recover a hard kernel deadlock or guarantee that a completely frozen
machine restarts. No hardware watchdog, firmware boot-selection change,
security relaxation or resident post-startup monitor is introduced. The
already accepted manual recovery remains necessary for those failures.

See the [sanitized R1a recovery record](validation/build34-r1a-recovery-20261120.json)
and the [earlier R1b startup failure](BUILD34-RING-BACKPRESSURE.md#november-20-startup-failure-and-r1a-disk-recovery).
