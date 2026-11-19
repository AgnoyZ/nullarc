# PR28 bounded publication wait on build34

**Current local setting:** on 2026-11-18 the owner requested daily waiting for
ordinary applications, and the existing installed plugin's persistent
configuration was enabled. WindowServer remains excluded and the default
budget remains 250 ms. See the
[daily configuration record](#2026-11-18-owner-selected-daily-configuration).
The source-integration and earlier trial policies below are historical; the
compiled policy itself remains opt-in.

On 2026-11-16 the owner requested continued PR28 repair, then specifically
focused the task on wait timing. This source change derives from default
`upstream34/vram-layout-fix` at
`dd32109ed02c37f8e536a061c530aafa3b7f96de`, retaining the preceding four plugin
PR backports and A1/A2/corrected-A3. Original34 kernel, native ABI, production
phxctl, PhxAccel, admission checks and licenses are unchanged. Build41/build42
remain withdrawn. No driver installation, loading or GPU trial is authorized
or performed by this source integration.

## Upstream input and findings

The reviewed input is upstream [PR28](https://github.com/luuumi-dev/nullarc/pull/28),
head `317092664427f3fe7650f5fa08e8fe1b7ba011df`, base
`8aba872560a3c9b7dc7a0ddebfad001c6dddf315`. Its one changed-file Git blob was
independently verified through GitHub's API. The component retains
PolyForm-Noncommercial-1.0.0; no third-party library or binary is added.

The upstream change waits for execution and surface publication before an
application's writer `commit` returns. It excludes WindowServer, completion
handler waiting and the execution queue. Its reported camera result is an
upstream single-machine observation, not a result obtained in this batch.

The wait loop has no deadline while `_completionReady` remains false. A CPU
condition double reproduced four repeated untimed waits, then deliberately
exited with status 90. It did not hang the real driver or execute GPU work.
Also, the upstream post-submit writer check enumerates `_parts` while the
execution worker replaces and removes those entries. This concurrency hazard
is a source finding; no live corruption or crash is claimed. Queue-label
comparison does not establish execution-queue identity or target inheritance.

## Local repair

- Capture surface-write eligibility immediately after sealing, under the
  submission lock and before the buffer is made pending. Allocate/enter a
  separate publication group only for eligible, explicitly enabled buffers.
  Do not inspect mutable submission parts from the post-submit wait.
- Leave that group after `_completionReady` is set and its condition lock is
  released. Completion handlers have been enqueued, but their execution is
  excluded from the barrier. A terminal execution error is still an error;
  a signalled barrier does not relabel command-buffer status as success.
- Use `dispatch_group_wait` with `dispatch_time(DISPATCH_TIME_NOW, ...)`.
  The installed SDK's `dispatch/time.h` documents the default clock as
  `mach_absolute_time`, rather than wall time. Record actual elapsed duration
  with process-local `CLOCK_UPTIME_RAW` samples. Do not add requested sleeps or
  pass timestamps between processes with different clock domains.
- Tag the actual execution queue with a dispatch-specific key. Skip this
  additional wait on that queue and queues targeting it. A different queue
  merely named `nvmtl.execution` does not bypass the guard.
- On expiry, return an unsuccessful internal wait result, trace actual elapsed
  time and emit rate-limited explicit diagnostics. Preserve pending parts,
  resources, reservation, error and status. Do not cancel/free uncertain work,
  forge completion or claim that surface publication has succeeded. Later
  completion still signals every waiter normally.

## Controls and limits

At the source-integration checkpoint, the build34 **default remained off**,
consistent with the wait-promotion HOLD.
Only exact `NVMTL_SURFACE_COMMIT_WAIT=1` opts in; WindowServer is always excluded,
and presence of `NVMTL_NO_SURFACE_COMMIT_WAIT` overrides opt-in. Nothing in this
batch sets these variables on the machine or installs the compiled plugin.

`NVMTL_SURFACE_COMMIT_WAIT_MS` accepts decimal 1..2000 milliseconds, with a
250-millisecond default. Invalid, negative, overflowed or out-of-range values
fall back to 250; zero never becomes an infinite wait. This is a wait budget,
not a hard real-time scheduling guarantee. Scheduler or kernel stalls can
delay observation of expiry. The existing explicit `NVMTL_DEBUG_WAIT_EACH`
diagnostic is unchanged and bypasses the additional wait.

This deliberately bounded, opt-in adaptation does **not** preserve upstream's
unconditional guarantee that an enabled writer is finished before every
`commit` return: expiry explicitly leaves publication unconfirmed and keeps
Metal's asynchronous submission state intact. An application requiring pixels
must establish successful completion before handoff. Consequently this change
does not establish that Tencent Meeting corruption, the existing IB wrong
value, WindowServer's separate scheduling/fence stall, UI stutter or FPS is
fixed. Enabling this wait by default, changing the native fence policy, and
accelerated desktop adoption remain on HOLD pending separate scope and real
GPU evidence.

## Validation and rollback

`make test-nmplugin-surface-commit-wait` compiles the actual policy, budget,
prepare/wait helpers, writer classifier and completion method with CPU doubles
under ASan/UBSan. Ten tests cover strict controls, budget boundaries, no-surface
fast paths, completion after simulated publication, pending handlers, expiry
without resource retirement, late completion, actual sampled elapsed time,
queue identity/targets, label collision, eight simultaneous waiters, terminal
error preservation and production wiring. Timeouts bound each subprocess.

Existing A1 and four-PR plugin tests, A2/A3 host regressions, native x86_64
plugin compilation, baseline-warning comparison, release signature and entry
point checks are recorded in
[`validation/build34-pr28-wait-timing-20261116.json`](validation/build34-pr28-wait-timing-20261116.json).
Compiled bundles and raw evidence stay ignored and local; no binaries are
published. These are host/compile results, not hardware acceptance.

Rollback is `git revert` of this isolated source commit after reviewing later
dependencies. Keep the accepted earlier PR/A1/A2/A3 commits and history. There
is no deployment to undo. Retain the explicit default-off policy unless a
separate hardware-scoped decision changes it.

## Subsequent requested installation and desktop prerequisite test

After source integration, the owner requested installation/testing and then a
desktop-acceleration test. Preparation crossed local midnight; the hardware
trial and recovery occurred on **2026-11-17**, on macOS 26.7.2 / `25G332`.
The source was default commit
`52d68e68731aead50eda41ce427d4c5112659d4c`. The original34 kernel image,
native ABI, production helper, A1/A2/corrected-A3 and existing admission checks
were preserved. This was a fresh, single-use scope; no consumed trial packet
was replayed and neither withdrawn build was a candidate.

The signed x86_64 release plugin was installed by an atomic bundle exchange
after a complete verified backup. A new process loaded that exact installed
image, verified the PR28 group ivar and completion method, and performed no
device creation or GPU work. All 18 runtime file-access checks passed. This
also confirmed that the release constructor clears inherited `NVMTL_*`
environment variables. A future process-local opt-in test must set its controls
after loading the plugin and before first policy use; passing an environment
variable before load alone would not establish that PR28 was enabled. Global
configuration was not changed.

Desktop admission then ran the unchanged original34 native integrity probe,
before any accelerator/display claim or Metal execution. One initialization
passed the original compute, graphics and queue-adoption checks. The probe
submitted two guarded dispatches; pass 0 verified, but pass 1 failed at byte
`0x2010`: actual `0xde`, expected `0xdf`. This is the same mismatch as the
earlier original34 control. No MEC range treatment was applied in this trial.
The three native wait calls measured 7,324 ns, 22,162 ns and 26,250 ns; the
second dispatch reported retirement but failed byte validation. These are
native wait measurements, **not PR28 publication-wait timing evidence**.

On the failure, the test retained the native client's mappings/resources,
restored the exact pre-install plugin bundle and requested one recovery reboot.
Independent readback confirmed original34, GPU-off, the firmware framebuffer,
zero trial GPU calls on the recovery boot, no active probe/shutdown, and removal
of the consumed startup job. All 46 protected files, two links and 347 EFI files
(including 148 Microsoft files) matched their prior manifests; security and
kernel collections were unchanged, with no new matching diagnostic report.
No EFI/NVRAM write, kernel replacement or binary upload was performed.

The installation/loader stage passed, but the native prerequisite failed.
Consequently desktop acceleration was **not enabled**, the PR28 GPU wait path
was **not exercised**, and no FPS, GUI-stability or camera result is claimed.
The default wait remains off; the IB wrong value and desktop/wait-promotion
HOLDs remain unresolved. This prerequisite result does not establish PR28's
effectiveness or the cause of the native mismatch. Sanitized evidence is
[`validation/build34-pr28-install-gate-20261117.json`](validation/build34-pr28-install-gate-20261117.json);
exact manifests, controller checks, binaries and raw logs remain private and
ignored. The source change remains on default, while the installed plugin is
back at its pre-test version.


## Fixed-kernel real-GPU wait trial, 2026-11-17

After the bounded desktop result recorded in
[BUILD34-DESKTOP-VALIDATION.md](BUILD34-DESKTOP-VALIDATION.md), the owner
requested continued PR28 real-GPU waiting, longer stability and FPS acceptance,
in that order. This trial used default source
`857434ee3282281edd53f36706494baf1a8cb4ae`, the same already tested build34
compute-sync kernel and the previously built release PR28 plugin. The plugin
source inputs still matched default byte for byte. Only the installed plugin
changed relative to the accepted kernel/runtime trial; its original complete
bundle was backed up and restored. Withdrawn builds were not candidates.

An initial preparation refused an unsigned loader-only probe. That packet
was retired before installation, EFI writes, a startup job or GPU calls. A
new signed packet passed 70 CPU/controller methods, a dynamic-library
wait-observer self-check and 18 credential-dropped runtime access checks.
The observer passively intercepted the production publication-group wait in
the test process, without modifying the production plugin. Controls were set
inside that process after loading. Default-off policy and WindowServer's
exclusion were retained. Planned subsequent timeout instrumentation would
gate completion signalling in the test process only; it was never reached.

The fixed kernel loaded, with the original restored to disk before GPU
initialization. Original compute/graphics and both queue-adoption checks
passed. Both native dispatches verified their full 16-KiB arenas without a
mismatch. The PR28 IOSurface writer then reached its observed publication
wait, but failed the probe's check that natural `commit` return had established
successful completion. The probe held its resources until managed recovery.
The normal-success record and pixel checks were not completed.

**This is an unaccepted PR28 result.** The observer reached a combined failure
condition covering a nonzero wait result, a still-pending group or command
status other than Completed; it did not preserve those three values separately.
No actual elapsed duration or specific completion-error subtype can be claimed
from that attempt. It does not establish a GPU hang, a PR28 timing defect or
an observer defect. Further diagnosis must preserve those values before
asserting. The induced-timeout trial, longer stability and FPS were not run.

Recovery restored the exact plugin, startup job, allowlist and original
build34 disk image and rebooted once. Independent readback re-parsed the
native evidence, verified all 46 protected files and 347 EFI files, removed
the exact nine-file recovery subtree and consumed restore job, and confirmed
GPU-off, the firmware framebuffer, no test clients or shutdown scheduler,
EFI unmounted and zero new matching diagnostic reports. No subsequent test
was armed at that readback. Raw records and binaries remain local and ignored.
Sanitized evidence is in
[validation/build34-pr28-fixed-gpu-wait-20261117.json](validation/build34-pr28-fixed-gpu-wait-20261117.json).


### Follow-up diagnostics: natural waits passed; observer count refused

A fresh diagnostic packet based on default `ef5a41d961b0645838d33f85694388f166999683`
kept the same kernel and plugin, changing only process-local observation.
It preserved the group result, remaining group state, command status and error
before assertion. Three real-GPU waits returned zero with their groups ready,
command status Completed and no command error. Their measured durations were
**158,495,906 ns**, **454,392 ns** and **406,061 ns** with the existing 250 ms
budget. Both IOSurface sampler passes reached the final summary, establishing
32 pixels / 128 channels matched after three completed commands.

The probe then exited 23 because its own summary incorrectly required one
eligible command and two ineligible sampler commands. Production compute
`setTexture:atIndex:` conservatively marks storage-capable surface textures
dirty, so those sampler commands can also receive publication groups. This
is an observer expectation error, not a failed command. It does not determine
the unresolved failure subtype of the preceding attempt.

The first real natural-wait/pixel evidence is retained, but the complete test
packet is not accepted and the timeout stage did not start. Independent
recovery and retirement again verified the original plugin, original loaded
kernel, all 46 protected files and 347 original EFI files, no held clients,
GPU-off and zero new matching diagnostic reports. There was no automatic
retry. The next probe must count the actual three eligible surface commands
and add a separate buffer-only operation to test the no-surface fast path.
Its timeout workload must be bounded independently and establish real late
completion and output; no wait-policy or driver-byte change is required by
this observer correction. Longer stability and FPS remain untested.

### Complete bounded wait acceptance after observer correction

A fresh packet based on default
`85e8872d96643489e5fa0ff7be651b46e14806a0` corrected only the probe's
eligibility expectation and added a genuine buffer-only control. The same
compute-sync build34 kernel and exact release plugin were retained. The
packet passed 70 CPU/controller methods, both CPU observer self-checks and
18 runtime-access checks before its single activation. Both native dispatches
again verified their complete 16-KiB arenas with no mismatch.

The real publication waits for three eligible commands returned successfully
in **38,432,698 ns**, **232,346 ns** and **300,062 ns**, with a 250 ms budget.
Each group was ready, each command was Completed and no command error was
present. Two sampler passes verified 32 IOSurface pixels / 128 channels.
The fourth, buffer-only command had no publication group, called no group
wait and verified all 256 output bytes.

A separate real render used the 1 ms budget. A bounded gate in the test
process delayed that command's completion signalling; production plugin bytes
were unchanged. The observed wait returned unsuccessfully after
**1,096,975 ns** (whole `commit`: **1,200,369 ns**), with its group still pending,
command status Scheduled and `_completionReady` still false. Releasing the
gate allowed genuine completion; subsequent IOSurface locking verified
16 pixels / 64 channels. No completion was forged, and this controlled case
does not establish recovery from arbitrary GPU hangs.

**This complete, bounded PR28 real-GPU wait packet passed.** Independent
readback re-parsed native and Metal output and matched the controller
receipts. It then verified exact restoration of the original loaded build34,
original complete plugin, 46 protected files and 347 original EFI files;
removed the exact nine recovery files, restore-only job and candidate plugin
stage; and confirmed GPU-off, EFI unmounted, no test clients and zero new
matching diagnostic reports. No later test was armed at that readback.

The short desktop tail contained three samples and two validated intervals;
it is not longer stability or FPS acceptance. The successful packet does not
explain the earlier unresolved combined failure. Default-off policy and
WindowServer exclusion remain intact; no permanent adoption, camera repair,
UI-stutter repair or general performance result is claimed. Longer stability
must pass before the separate FPS stage. The sanitized evidence file retains
the earlier failed packets and appends this successful follow-up.

## 2026-11-18 owner-selected daily configuration

After the accepted local installation and subsequent monitor shutdown, the
owner explicitly requested PR28 waiting on by default for daily application
use. The existing supported configuration file
`/Library/GPUBundles/nvmtl/nvrm610.conf` now contains this additional setting:

```ini
NVMTL_SURFACE_COMMIT_WAIT=1
```

All previous configuration bytes are preserved. No budget override or
WindowServer policy change was added. The compiled default remains opt-in;
the local persistent configuration opts newly launched ordinary applications
in automatically. The unchanged release constructor clears inherited knobs
before reading this file, so a launchd environment setting alone would not
establish the requested behavior. Existing applications cache their policy
and must be reopened to read the new setting. WindowServer is explicitly
excluded in the production predicate even when the setting is present.

The wait budget remains 250 ms. Expiry still preserves pending work and
reports publication unconfirmed; it neither forges completion nor waits for
completion handlers. Kernel source/image, plugin source/image, ABI and all
accepted A1/A2/corrected-A3 and IB-fix behavior remain unchanged. The runtime
source checkpoint is still `1d4968fbc2ce988c77bdd85b2ec36f435b57f496`.

The local startup-integrity policy records the exact original and new
configuration digests. Its scoped allowance changes only this protected
configuration entry in a copy of the old contract; the frozen contract and
all other protected entries remain intact. Startup telemetry distinguishes
the compiled opt-in policy from the enabled local daily configuration.
The resident installation/hang monitors remain disabled.

All 46 CPU methods passed: the existing ten ASan/UBSan production wait tests,
eleven exact-allowance/configuration tests and the retained 25 startup-policy
tests. A preparation guard initially refused a nonunique telemetry edit before
any live change; the refusal was retained and the edit narrowed to the actual
startup record. After application, new administrator and ordinary desktop-user
processes loaded the exact installed release plugin, verified its image and
PR28 ABI, and observed the persistent opt-in after inherited controls were
cleared. Both loader checks created no Metal device, queue or GPU resources.
All 18 runtime file-access checks passed. Independent readback confirmed the
same WindowServer, active acceleration/desktop controls, zero copy failures
or skips, no new matching diagnostic reports and unchanged security settings.

No application restart, WindowServer restart, GPU test workload or reboot was
performed for this configuration change. The earlier bounded GPU wait evidence
is retained; it is not a new long-term stability, camera, stutter or FPS result.
The next boot with the updated local policy has not been tested.

For an owner-requested rollback, restore the saved pre-change configuration
and its matching startup-policy snapshot together, preserving unrelated
settings and the disabled resident-monitor policy. A subsequent setting change
also requires reopening affected applications. Exact private backups, loader
output and receipts remain local; no binary or raw diagnostic is published.
The sanitized result is
[`validation/build34-pr28-daily-config-20261118.json`](validation/build34-pr28-daily-config-20261118.json).

## 2026-11-19 Weather investigation: release timeout logging

The owner reported trails after opening Weather while the accepted
build34/VBL/AML/render-clear/startup-order runtime was active. A new finite
Weather observation added no entries to the filtered release log. That result
cannot exclude a PR28 publication deadline: the installed release logger's
failure classifier omitted the actual timeout message.

`nvmtl_surface_commit_wait` formats a message beginning
`surface commit wait: deadline expired` and explicitly leaves publication
unconfirmed and pending work retained. The release `nvlog` implementation
only sends messages accepted by `nvmtl_log_failure` to syslog. This message
contains none of that classifier's existing failure keywords, so even a
genuine deadline message is discarded. The four checked kernel error counters
also are not a count of this userspace publication deadline.

The source-only correction adds that specific message fragment to the
existing failure classifier. No wait budget, caller policy, WindowServer
exclusion, command status, completion, resource lifetime, publication ordering
or rate limiter changes. It does not enable general tracing, add a monitor or
log successful waits. It does not establish that Weather actually timed out
or that a timeout caused the reported trails.

The new CPU regression compiles the actual release `nvlog`, its rate limiter
and failure classifier, using the timeout format extracted from the
production wait helper. Only syslog is replaced with an in-process collector;
no synthetic driver failure is emitted into the system log. The baseline
fails because the timeout is dropped. The correction passes four ASan/UBSan
methods: the actual timeout and its pending-publication qualification reach
the collector at error severity; 13 existing failure examples remain visible;
successful waits and unrelated deadlines remain quiet; and the original
eight-message/4,096-call rate limit remains in force. The unchanged ten-method
production wait suite and `make test` also pass. These are CPU checks, not GPU
execution or visual acceptance.

```sh
make test-nmplugin-release-logging
make test
```

**The logging correction is not installed.** No complete candidate plugin
bundle was built or deployed for this follow-up. The accepted installed
plugin and its admission/recovery pins are unchanged and still have the old
filter. Absence of its release messages must not be described as excluding
publication deadlines. An actual trial of the corrected logger requires a
fresh compatible plugin scope and installation authorization; do not reuse
consumed deployment or restart scopes. Source rollback can revert this
isolated classifier/test change and does not affect the running plugin.

The separate Weather observation and its limitations are recorded in
[`validation/build34-weather-trails-20261119.json`](validation/build34-weather-trails-20261119.json).
