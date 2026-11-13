# Independent allocation observer source candidate

This uninstalled follow-up to the [one-attempt capture helper](ALLOCATION-CAPTURE-CANDIDATE.md)
addresses the recovery dependency identified during source review. The existing
monitor must remain free to recover while snapshot collection is blocked,
refused or dead. No actual failed-boot snapshot has been obtained and the
allocation root cause remains unconfirmed.

## Process relationship

`tools/allocation_observer.py` is intended to run as a separate peer process.
It has no recovery command, callback, subprocess, IPC request or GPU workload
interface. The existing monitor neither invokes nor waits for it. A future
reviewed launcher must preserve that relationship and must not introduce a
join, wait, synchronous hook or mandatory acknowledgement in a fallback path.
There is no launcher, LaunchDaemon, startup edit or installed integration in
this source candidate.

The observer arms a macOS vnode watch on the explicitly supplied diagnostic
directory, takes its initial report-name/file-identity inventory, and invokes
the existing baseline helper once. It then rescans immediately and on file
notifications. A newly discovered regular `WindowServer-*.ips`,
`WindowServer_*.ips`, or corresponding `.spin` file triggers the existing
failure helper once. That helper still requires the same boot, service,
build and loaded-image identity as its baseline. No additional reader,
selector, reset or reaping behavior is introduced.

This requests a snapshot on the first qualifying discovery instead of waiting
for the monitor's three-report recovery threshold. It neither changes that
threshold nor guarantees that discovery or capture will finish before the
monitor recovers. A capture that overlaps the recovery decision must not
delay recovery. Kernel-wide hangs or resource starvation can still prevent
either process from running; process independence is not a hard real-time
guarantee.

## Trigger and ordering limits

The observer watches report-file metadata, not the report contents, GPU fences
or kernel logs. It does not parse or correlate PIDs, crash UUIDs, exception
causes or RADV samples. New means a name absent from the initial inventory or
a different device/inode for that name. Files present in that inventory are
not new merely because their contents change. Symlinks and directories are
not reports. A file that disappears during enumeration supplies no evidence.
Creation of a diagnostic file is a trigger, not proof of GPU causation or of a
completed/valid crash report.

Notifications can coalesce. If a discovery contains multiple candidates, the
lexicographically first name is a deterministic representative, not a claim
about chronological crash order. Their count and the chosen name/file identity
are retained privately. Arm-before-inventory and an immediate post-baseline
scan cover persistent files created during baseline setup; transient files
removed before a scan can still be missed.

A report can appear during baseline collection. Its presence does not prove
that the baseline preceded that failure or the GPU workload. This helper
does not enforce workload startup ordering. A future execution plan must
separately establish the service's availability and the baseline/workload
boundary; an observer marker alone authorizes no GPU action. The first-four
record and counter-saturation limits of build 37 still apply.

## Bounds and private evidence

The caller must explicitly select a 1–300 second observation window, reader
path/hash, build, expected loaded-image UUID, report directory and fresh output
directory. The live host check remains administrator Intel macOS. The report
directory must be owned by the collecting user and not world writable; its
path must have no symlink components. Device/inode, type, ownership and
world-write permission are rechecked during observation. Existing trusted
installation-path requirements also apply to both Python helpers, the
interpreter, imports and reader.

Each scan examines at most 4,096 entries, including unrelated files. One
initial inventory and one immediate scan can be followed by at most 64
notification-driven rescans: at most 66 scans total. An event storm, directory
replacement/rename, malformed input, collector refusal or other error stops
observation without retry. A quiet directory uses a timed vnode wait, not
periodic polling. The fixed window starts before watch setup and baseline;
the deadline is checked again after scans and trigger persistence before
invoking the failure helper. That helper uses its own existing wait budget.

The window bounds observation decisions, not total wall time. File operations,
notification setup/teardown, fsync and kernel-blocked IOKit can be
uninterruptible. The observer can remain blocked even after its window. The
independent monitor must continue without needing to kill or reap it. No
existing monitor, WindowServer or GPU process is signalled by this observer.

Existing capture helpers retain their exclusive attempt markers, 0700 root,
0600 files, private gitignore and no-overwrite behavior. `observer.started`
records baseline hash and window metadata. `observer.trigger.json` records the
private trigger before requesting the failure snapshot; it is not proof that
the failure read ran or completed. `observer.json` is exclusively published
after completion with outcome `captured`, `window-expired`, or `event-limit`.
Only `captured` includes the SHA-256 of the completed failure file. Partial
output is never promoted to a successful snapshot. Report names, paths,
file identities and raw evidence must stay private.

## Offline checks and deployment boundary

`tests/test_allocation_observer.py` covers ordering, persistent files arriving
during baseline, old/replaced report identities, coalescing, one failure read,
deadline crossing, scan/event caps, refusal, interruption, no overwrite,
directory metadata boundaries and setup cleanup. One test exercises the actual
collector and actual reader source against the existing fake native transport.
A native kqueue case uses only a temporary directory on macOS/BSD; Linux
explicitly skips that case. Neither opens a target service.

Two separate-process scenarios use a fake collector and a **stub recovery
process**. The stub completes while the observer is blocked and after it has
been killed. They verify the proposed process relationship, not execution of
the installed monitor or proof of real firmware recovery. No old boot script,
GPU helper, driver, runtime or system recovery command is executed by the tests.

The manual `allocation-capture-check.yml` now runs the unchanged capture suite
and the observer suite on Ubuntu and `macos-15-intel`, with no driver build or
artifact upload. Actual launch ordering, installation, failed-boot collection,
lock behavior and hardware recovery remain untested. The consumed M2/reboot
grants remain spent; source preparation authorizes no deployment, arming,
initialization, GPU work, startup change or reboot.

The local focused pass on 2026-11-14 completed 23 observer tests, including the
temporary-directory native kqueue case, and all 21 existing capture tests.
The five executable/test/workflow input hashes remained unchanged during that
pass. Clean-commit and hosted verification are recorded after synchronization;
these focused results alone are not a full-suite pass.
