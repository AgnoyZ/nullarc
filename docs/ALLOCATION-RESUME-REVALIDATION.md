# Allocation investigation: continuity and retained-input revalidation

Status, 2026-11-14: **same Goal active; retained inputs reverified; Phase A
still unperformed**. This follow-up supersedes the earlier current-state
continuity blocker in the [install-packet record](ALLOCATION-INSTALL-PACKET.md).
It does not replace that record's historical failed activation or consume a
new target-operation grant.

Later on the same date, the [capture-runtime delivery](ALLOCATION-CAPTURE-RUNTIME.md)
closed the trusted interpreter/helper staging gap below, with focused tests
on the system interpreter and independent private read-back. It did not
install a kernel, run a snapshot reader or connect the observer to startup.
The Goal observations here describe this historical continuation; later
execution must verify its own actual continuity state.

## What changed

The supported user-origin lifecycle operation restored the existing Goal to
`active`, preserving its objective and budget. A subsequent saved-session
launch and the explicitly requested Full Access continuation were observed.
The original per-boot claim remains present. The earlier helper-launched
process exited after the cooperative interruption for the permission switch;
its retained exit status is not evidence of driver failure.

Fresh boot metadata matches the helper's installation boot and the retained
deployment baseline. These launches therefore demonstrate continuation on
that boot, **not an end-to-end reboot test**. The helper must still refuse an
inactive Goal and a consumed per-boot claim. No Goal database was directly
changed and no claim was removed to obtain this continuation.

The repository's default continuation helper remains unchanged. The installed
session-specific copy and manual entry point were separately adapted under
the user's explicit Full Access instruction. Their updated hashes and local
verification receipts remain private; this does not grant driver deployment,
snapshot reads, M2 or reboot operations.

## Fresh read-only results

After the permission switch, metadata and root-owned retained-file reads
succeeded. The scoped checks found:

- One matching PhxBringup service, still **build 36**, with the expected loaded
  image and matching before/after boot and service identities.
- **IONDRVFramebuffer** present; the two available display switches read zero.
  Two other queried switches were unavailable, not assumed zero. The selected
  NVRAM arming value and five named pending/M2/one-shot markers were absent.
  The bounded named-helper query found no match; it does not exclude all
  background GPU activity.
- All eight selected installed-input hashes, sizes and ownership/mode checks
  matched the retained preflight baseline.
- The original native packet's **57 manifest entries / 3,333,129 bytes** and
  install/rollback packet's **436 entries / 106,164,036 bytes** matched their
  retained hashes. The exact kernel and reader identities published in the
  [native-build record](ALLOCATION-LIVE-PREFLIGHT.md) still match. This verifies
  retained backup bytes; EFI was not mounted or compared with the live volume
  again during this follow-up.

These observations are time-bounded preflight evidence. They do not authorize
an operation or replace identity checks immediately before a future operation.
Recovery remains operator-attested, not agent boot-tested.

The earlier restricted reads failed to observe boot, registry, loaded-image
and switch state. Their empty arrays and false-valued summary fields must be
read as **unverified**, not hardware absence. A separate summary parser also
mistook an active nested launchd coalition for the job's top-level state. The
raw output instead says `not running`, active count zero and no top-level PID.
Both original evidence and the superseding interpretation are retained
privately. No launch or target operation was replayed to correct the summaries.

## Hosted validation and remaining admission gaps

Existing automatic run **43539539120**, at commit
`0f7b19b6f0f23e63be5c4e43a738b2f07a29b928`, completed successfully. Its
`source-tests` and `macos-kexts` jobs both succeeded; the run retained **zero
artifacts**. This is hosted source/build validation, not target loading or GPU
execution. No new workflow was dispatched and the unchanged local 523-test
suite was not rerun.

The native packet does not contain `tools/allocation_capture.py` at its
retained `SOURCE/tools` path. A trusted capture helper, supported interpreter
and import closure have not been staged and verified for root execution.
The tested user-installed interpreter cannot be assumed to supply a trusted
root runtime merely because its executable hash can be recorded. This is a
remaining execution-packet input, not a reason to run a different reader or
rebuild the kernel.

Before [Phase A](ALLOCATION-EXECUTION-PLAN.md#phase-a-prove-passive-read-feasibility-on-the-firmware-desktop),
finish that concrete private runtime/delivery scope, retain the exact rollback
and independently usable recovery procedure, and obtain separate exact
unconsumed scopes for the proposed install/load, each passive read and any
normal firmware-desktop reboot. Full Access does not replenish consumed grants.
Do not deploy or run the legacy initialization scripts, initialize the GPU,
arm M2 or escalate after a refused operation.

The build-37 candidate remains uninstalled and unread on the target. The
allocation root cause and real reboot/resume behavior remain unconfirmed.
The [sanitized validation record](validation/allocation-resume-revalidation-20261114.json)
keeps these limits separate from the completed checks.
