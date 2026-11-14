# Preserve helper failures through the reference startup callers

Status, 2026-11-14: **source correction; not installed or hardware validated**.
This fixes the failure propagation reproduced by the
[startup audit](ALLOCATION-STARTUP-AUDIT.md) and
[two-engine handoff review](ALLOCATION-QUEUE-HANDOFF.md). It does not identify
the retained allocation failure's root cause or complete a safe initializer.

## Corrected behavior

The reference `full.sh` previously continued after failed preparation,
register or MES commands. Its final helper pipeline could lose status 74/75
to `tail`, and a successful final shutdown-process command could return zero.
The reference `phxboot.sh` then filtered initializer output through grep and
continued into claim and display setup without checking either helper.

The correction makes these specific changes:

- `full.sh` stops on a failed preparation, watchdog-launch, GART or MES command.
  After each register/final-helper pipeline it immediately captures both
  `PIPESTATUS` values. A failed helper's original status takes precedence;
  if the helper succeeded but tail failed, that filter failure is returned.
  Failure exits before the existing watchdog-cancellation command.
- `phxboot.sh` immediately captures the initializer's own pipeline status.
  Initialization failure prevents claim. Claim failure prevents subsequent
  setup. A successful initializer without matching diagnostic text is still
  successful; log text is not an execution result.
- Firmware-desktop failure uses the existing release/marker-removal pattern
  and exits with the original status. M2 failure requests the existing
  recovery path with that status. Other existing `m2_fail` callers retain
  their previous default exit status. Recovery thresholds and operations
  are unchanged.

This is an explicit caller-status check, not a global strict-shell mode.
No C helper, kernel ABI, readiness guard, VM budget, queue policy, pin direction
or resource cleanup implementation changes.

## Verification and limits

The initial working-tree checks passed six startup-audit unit methods and
four selected status/filter unit methods, plus Bash syntax checks for both
reference scripts. The startup harness now pins the corrected monitor and
executes twelve guarded source-fragment scenarios, including initializer
statuses 17/74/75, claim status 23, firmware/M2 failure paths, output with and
without a grep match, and controlled blocking. All system commands are fakes;
no whole reference script or installed helper is executed.

The pipeline regression executes the exact extracted status guard with five
helper/filter combinations, including simultaneous helper and filter failure.
The completed fake-I/O C harness passed 52 transport, 20 completion, 16
submission-boundary and six compute/graphics handoff cases. The six handoff
outcomes run through both the extracted caller guards and the filter-only
negative control. Failed outcomes retain 74/75 and request no claim hook in
the checked composition.

The clean committed source `ae23e2d0bf6e07415ff7f7fa6a94296be562f9a2`
passed all **523 unit tests in 280.473 seconds** with Python 3.13.18, without
skips. Separate startup and transport runners also passed on that interpreter.
All 812 tracked input-file hashes matched before and after the run and in an
independent read-back; the checkout remained clean. The
[validation record](validation/allocation-startup-status-fix-20261114.json)
retains source identities and aggregate outcomes. Only this documentation and
that record change after the tested source checkpoint.

An initial run accidentally used the unsupported system Python 3.9.6. It
completed 523 tests with two errors: an unsupported `Path.write_text(newline=)`
argument and a capture-command timeout. That failed attempt is retained
privately and is not counted as a pass. The supported-interpreter run passed
the same source and assertions; no test, production deadline or guard was
relaxed. The timeout's deeper cause is not assigned by this comparison.

A requested read-only Claude review of the public script sources and diff
reported no blocking regression. It used no tools or plugins and supplies
advisory review, not execution evidence. Its implication that successful
background launch proves watchdog readiness is not adopted.

The filter-only negative control intentionally still demonstrates why grep
and tail cannot establish success. The checked composition must preserve
74/75 and request no claim hook after failure. Its claim/recovery hooks remain
fakes; this does not execute kernel claim or real recovery.

## Remaining execution boundary

Both scripts retain their **NOT RUN BY THIS REPOSITORY** banner. In particular,
the reference initializer still has bare GART/MES arguments, fixed-layout
assumptions, nested unaudited preparation and a global shutdown-process kill
on its successful path. A command reporting zero does not validate those
transitive operations. In particular, the shell starting asynchronous
`nohup shutdown` can return zero before the background child fails; actual
watchdog readiness is unproven. Its incompatible GART invocation should now stop
instead of allowing later commands to run. Do not deploy or execute this
patched legacy workflow as a replacement initializer.

This change also does not undo a compute adoption already accepted before
a later graphics failure, supply the missing resource-ownership contract,
provide baseline admission or make recovery independent of a blocked helper.
Those remain separate requirements in the
[execution plan](ALLOCATION-EXECUTION-PLAN.md). Installed startup, the pinned
native build-37 kernel/reader and the private EFI rollback packet are unchanged.
No target reader, GPU workload, arming or reboot is requested by these tests.
