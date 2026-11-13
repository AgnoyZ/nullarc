# Pre-fallback allocation capture source candidate

This uninstalled Python helper complements the [build-37 snapshot candidate](ALLOCATION-SNAPSHOT-CANDIDATE.md).
The build-36 failed boot produced verified RADV refusals but no candidate kernel
records. A software snapshot taken after automatic recovery would describe the
new boot, not the failed one. The allocation root cause remains unconfirmed.

The separate [independent observer candidate](ALLOCATION-OBSERVER-CANDIDATE.md)
adds bounded report-file notification handling in a peer process. The capture
helper itself retains its one-attempt contract, and the existing monitor is
unchanged.

## Existing monitor and proposed integration points

The reference `tools/phxctl/phxboot.sh` has three relevant control points:
the armed boot's `release`, `m2_fail` before changing fallback state and
rebooting, and the later `watch_hangs` path before recovery. Its early
unfinished-attempt recovery path may run before a useful baseline exists.
Reading the installed monitor confirmed the same control points; it was not
executed or modified. The reference monitor remains marked as unaudited for
execution by this repository.

Future integration would take a baseline after the service is available and
before releasing the authorized workload. Each failure path would request the
single failure capture before fallback actions. The existing fallback must
continue independently of capture success, timeout, refusal or helper death.
There is no hook, launcher, daemon, executable deployment script or monitor
change in this candidate. A baseline failure would leave no valid comparison;
it must not cause arming, rearming or a workload retry. Missing baseline on the
unfinished-attempt path must not delay recovery.

## Capture contract

`tools/allocation_capture.py` offers two explicit phases, with no default
reader, build, expected image or output path:

```text
allocation_capture.py baseline --out PRIVATE_NEW_DIRECTORY --reader ABSOLUTE_READER_PATH
    --reader-sha256 REVIEWED_READER_SHA256 --expected-build REVIEWED_BUILD
    --expected-image-uuid REVIEWED_LOADED_MACHO_UUID
allocation_capture.py failure --capture SAME_PRIVATE_DIRECTORY
```

These are interface descriptions, not authorized target commands. A future
installation/execution plan must supply reviewed paths and build provenance,
pin the Python helper/interpreter and reader, establish fresh authorization,
and preserve the existing recovery mechanism. The previous M2/reboot grants
are consumed and cannot be reused by making another directory.

The live entry points require administrator Intel macOS. Each phase reads four
fixed metadata commands, calls the standalone reader **once**, then repeats the
four metadata commands. They read the boot-session UUID, OS build, the single
PhxBringup service's registry entry ID/build and the loaded PhxBringup Mach-O
UUID from `kextstat`. Pre/post identities must match, and failure must match the
baseline. A different boot, service replacement, unexpected build, missing or
ambiguous loaded image, malformed identity or refused reader stops collection.
An expected Mach-O UUID must come from independently reviewed build/load
evidence; UUID comparison by itself is not cryptographic image verification.
No on-disk kext is substituted for the loaded image.

The reader's SHA-256 and file identity are checked before and after each phase.
The reader must be a regular, executable file owned by the collecting user
(root during live collection), without other-user write permission. Paths
containing symbolic links, including parent links, are refused. Configuration
and executables must be placed in trusted directories by a separately reviewed
installation; these checks do not secure hostile concurrently mutable parent
directories or authenticate operator-supplied expectations.

Only selector 31 is requested by the unchanged standalone reader. No Hello,
QueryInfo, sysctl write, fence/MMIO access, initialization, submit, reset,
reaper call, NVRAM change or reboot is added. Ordinary native-client open/close
bookkeeping and GPU-lock contention still apply as documented for build 37.

## Bounds, persistence and failure behavior

Each phase has one five-second aggregate subprocess wait budget, at most nine
child commands, no shell, a sanitized child environment, and a 128 KiB limit
per stdout/stderr file. Core dumps are disabled for children. On timeout or
handled interruption, the helper sends SIGKILL only to its own new child
process group and waits at most another 0.1 seconds. It does not signal any
existing monitor, WindowServer or GPU process. There is no automatic retry,
polling loop, background watcher or GPU operation mode.

This bounds user-space child waits, **not total wall time**. Process creation,
filesystem operations/fsync and kernel-blocked IOKit operations need not be
interruptible. Killing a reader is not a GPU reset or proof that its pending
kernel method was cancelled. A future supervisor must preserve fallback even
if the helper cannot exit; an inline shell call alone is insufficient. No
claim is made that a snapshot will always be obtainable during a hang or
durable after power loss on every filesystem.

Baseline creates a fresh 0700 output directory and a local `*` gitignore.
All evidence files are 0600. Failure reuses that directory but cannot overwrite
a previous failure attempt. Each phase first exclusively creates and fsyncs a
`.started` marker; it is retained on every exit, so the same phase cannot be
retried even when its reader failed. An existing directory is never cleared or
reused for a new baseline. Input evidence must be private, bounded regular
files owned by the collecting user; file symlinks and hardlinks are refused.

Raw metadata, reader stdout/stderr and per-command return/timeout statuses
remain private. A parsed result is fsynced before exclusive publication as
`baseline.json` or `failure.json`; the containing directory is then fsynced.
An `.incomplete` file or raw reader output is not a completed phase. A crash
between publication and removing the temporary hardlink leaves a file with
multiple links, which the next phase refuses. Failure checks that baseline
bytes did not change during capture and records their SHA-256. Exit failures
use fixed codes without printing command output, paths or identities.

## Evidence interpretation

The helper validates the complete version-1 reader JSON schema, exact category
order, record counts, uint ranges, status/hex agreement, ordinal order, queue
reasons and aggregate counters. It rejects counter regression or changed
retained records. Comparison reports occurrence differences and only records
added beyond the baseline's retained prefix. Raw Mach 2 remains numeric 2;
there is no inferred import stage or invented retirement observation.

When a category's first four slots were already full at baseline, its counter
can increase with **no new detailed record**. An empty `new_records` array
therefore does not mean no refusal. Saturated uint64 counters provide a lower
bound, not an exact difference. Counts include internal reaper calls and
repeated attempts; they are neither unique external requests nor RADV sample
counts. This helper does not correlate WindowServer PIDs or log samples; that
would remain a separate, private evidence review.

## Offline validation and limits

`tests/test_allocation_capture.py` substitutes all metadata commands and the
reader with fake processes. It checks the actual subprocess/file code,
identity bracketing, same-boot/service/build/image refusal, exact one-read
sequence, private output, no overwrite/retry, schema/history validation,
counter saturation, malformed input, timeouts, output limits and environment
sanitization. The manual `allocation-capture-check.yml` runs this same suite
on hosted Ubuntu and `macos-15-intel`, without native compilation or artifacts.

The local focused suite passed 21 tests on 2026-11-14. An initial full-suite
invocation reached 357 tests but 13 fixture groups refused the uncommitted
checkout at their existing source-preparation guard. That is not a full-suite
pass. The guard remains intact.

Source commit **`e2cb77bc7b1d0ff058744e1b7a1746da32e2a45e`** then passed all
**442 Python tests** in a clean committed checkout. The collector, tests and
workflow input hashes were unchanged throughout that replay, and the checkout
remained clean. The installed monitor's privately retained hash also remained
unchanged. No source-preparation check was weakened.

Manual run **`43470322660`, attempt 1**, passed all **21 fake-process tests on
each platform**: Intel macOS job `132040203328` and Ubuntu job `132040203851`.
Both source-integrity steps passed. The workflow opened no native service,
compiled no native driver and uploaded zero artifacts. The automatic full-stack
run `43470223092` for this source commit was cancelled; it is not a build pass.
The five source-commit files were independently downloaded through GitHub's
blob API and matched local bytes, with the remote ref/tree/parent verified.

The [machine-readable validation record](validation/allocation-capture-20261114.json)
records source identity, input hashes, counts, job IDs and evidence limits.

This candidate changes no driver, ABI, reader, installed monitor, runtime,
EFI or recovery settings. It has not been installed, enabled or run against a
target service. Fake-process results do not establish real kernel lock
behavior, collection during a failed boot, automatic integration or allocation
root cause. Source preparation authorizes none of those target operations.
