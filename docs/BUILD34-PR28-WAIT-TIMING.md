# PR28 bounded publication wait on build34

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

The build34 **default remains off**, consistent with the wait-promotion HOLD.
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
