# Build34 startup latency investigation

On 2026-11-18 the owner identified the slow phase as the Apple logo/progress
bar after selecting macOS in OpenCore. The accepted installation runs macOS
26.7.2 build 25G332, with runtime source
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496` on the default build34 branch.

## Historical observations: 2026-11-18

That boot's unified log records the framebuffer display hold from
16:39:16.432200 to 16:39:45.538749: **29.106549 seconds**. The protected
initialization script entered at approximately 16:39:33, within that interval.
Both pre-initialization admission and initialization deserve investigation;
this does not measure the owner's complete perceived progress-bar duration
or prove a single cause.

The script continued approximately 90.46 seconds **after** display release.
That bounded observation is not demonstrated progress-bar blocking time. It
remains intact; removing it cannot be reported as saving 90 seconds at the
progress bar. Readiness-loop maximum bounds are not unconditional sleeps.
The bounded log query found no actual disk/root-device timeout; boot-argument
names containing `timeout` are not timeout events. Early wall-clock calibration,
receipt modification times and mach ticks cannot be treated as one precise
clock or added into a power-button-to-desktop benchmark.

## Isolated memory-use candidate

A read-only warm-cache profile measured approximately 3–4 seconds in two
protected-file hash passes. The historical implementation reads an entire
file into a temporary bytes object before hashing it. The protected inventory
totals approximately 788 MB; its largest file is 369,213,440 bytes. These
profile timings are not a boot benchmark; nested timings must not be added.

[`build34_startup_integrity.py`](../tools/build34_startup_integrity.py) reads
every byte for the same full SHA-256 with a reused 1 MiB buffer and no cache.
It refuses observed file-size, metadata or resolved-path identity changes.
Those checks do not provide an atomic snapshot against a privileged writer.
An isolated private owner-wrapper candidate adds only:

```python
integrity = load('owner_startup_integrity', W/'build34_startup_integrity.py')
desktop.sha = integrity.sha256_file
```

Only the desktop module's hash binding changes. Route/support/plugin hashes,
expected digests, historical contracts and all admission gates are retained.
The proposed policy preserves all old entries, repins the wrapper and adds
the helper's hash. This original CPU-only utility copies no upstream component
or binary and changes no driver, native ABI, initialization or GPU wait.

## Validation

All **67 CPU tests** passed: 11 streaming-integrity tests, 25 actual bounded
policy tests redirected to the candidate, 11 existing daily-policy/historical
snapshot tests and 20 existing ACPI expectation-scope tests. Coverage includes
digest boundaries, one-buffer reuse, aliases, no cached digest, changed files
and read failures. The candidate also passed actual static/installed-runtime
checks and full EFI/recovery verification. EFI was verified read-only and left
unmounted. The bounded startup module and shell remain byte-identical.

For the largest file, two whole-file subprocess samples used 377,692,160 and
378,073,088 bytes of peak resident memory. The actual guarded helper used
10,735,616 bytes: approximately **97% less peak process memory** in this
single-file comparison, not total boot memory. Whole-file samples took
1.27–1.30 seconds; streaming prototype samples took 0.60–2.45 seconds and the
actual guarded helper took 2.19 seconds in its separate sample. **No elapsed-time
improvement is demonstrated.** These results do not prove faster boot, less
UI stutter, higher FPS or a repaired driver.

The [sanitized record](validation/build34-boot-latency-20261118.json) contains
derived results only. Raw logs, identifiers, EFI/policy snapshots, original
backups and the wrapper candidate remain local/private.

## Historical candidate and rollback

**The candidate is prepared, not installed.** This investigation changed no
live owner entry, policy, startup job, EFI, kernel or plugin. Acceleration and
desktop takeover stay active, daily PR28 waiting stays enabled, and resident
monitoring stays disabled. No startup job, GPU workload or power action ran.

At preparation, the separately withdrawn S5 candidate remained loaded pending
an ordinary restart. That original-ACPI restart prerequisite was subsequently
completed; see the
[original-ACPI restart record](validation/build34-original-acpi-reboot-20261118.json).
Later authorized VBL, AML buffer and render-clear plugin trials changed the
accepted live scope. The historical hashing wrapper is not a current deployment
candidate: it must not be replayed or installed against those later expectations.

Any future helper treatment requires a fresh scope derived from the current
installation, exact-identity checks, saved wrapper/policy and the new helper pin.
Never replay a startup
job or bring-up in the running boot, shorten hardware waits or weaken gates.
A future rollback must match the exact installed candidate, restore only the
saved wrapper/policy and remove only the exact added helper. With no activation
performed, leaving current owner files intact is the current rollback state.
A later manual boot comparison is required for any boot-speed claim.

## Current investigation: 2026-11-19

The owner again reported slower startup than original nullarc. The current
default-build34 installation runs macOS 26.7.2 build 25G332 with the later VBL,
AML buffer and render-clear plugin scopes. This investigation reads existing
startup evidence and profiles only existing read-only admission functions;
it does not rerun initialization or change that installation.

### Actual boot evidence

The kernel's `PhxAGDC:` messages record display hold from 14:07:50.949462 to
14:08:17.296025: **26.346563 seconds**. This is a new measurement, not the
previous boot's 29.106549 seconds. The script log entered at approximately
14:08:10 and reported display release at 14:08:17. Its timestamp resolution
is one second: approximately **19–20 seconds of the hold precede script
entry**, with approximately **7 seconds from script entry to release**.
These are not complete OpenCore-to-desktop or power-button-to-desktop times.

The script ended at approximately 14:09:48, roughly 91 seconds after release.
The approximately 90-second observation loop follows `release` in both the
installed script and original upstream script pinned at
`3497d87b229e4839d8d2a03ebe9127f2a30f332b`. It is not evidence of 90 seconds
spent blocking the progress bar. That pinned upstream launch job starts the
shell directly; the current owner entry adds policy, historical-contract,
protected-file, loaded-identity and EFI/recovery admission first.

Same-boot `mach_absolute_ticks_v1` receipts, with matching 1/1 timebase, place
desktop readiness **16.041575367 seconds after guardian readiness**. This
interval starts after earlier checks and overlaps other events; it must not
be added to the display hold or treated as total startup duration. Receipt
file modification times are not used to calculate this interval.

### Read-only warm profile

One sequential profile of existing checks produced these nonoverlapping stages:

| Stage | Seconds |
| --- | ---: |
| Owner wrapper construction and static admission | 11.637908 |
| Loaded kernel identity | 1.286356 |
| Installed checks, including repeated static admission | 4.776677 |
| Full EFI/recovery verification | 3.484623 |
| Total of these sequential stages | 21.185564 |

Across those stages, SHA-256 itself used **10.749050 seconds** in 1,797 calls;
whole-file `read_bytes` calls used another 2.784552 exclusive seconds. These
function results are already inside the stage totals, not additional time.
Nested cumulative profile entries must not be added. The protected inventory
contains 45 present files totaling 787,782,761 bytes and one intentionally
absent kill-switch entry. Repeated static calls hash the present files again;
startup and guardian also run independent admission paths. This profile is
warm-cache, sequential and instrumented, not a cold-boot comparison of those
concurrent processes. It cannot assign 21.19 seconds of this boot to checks
or promise a corresponding speedup.

The first profile completed its read-only gates but lost its timing output
when optional inventory statistics attempted to stat the absent kill switch.
No missing marker was created. The corrected collector saves timings first,
records absent inventory entries without changing admission semantics, and
completed its gates and bounded log query. The full EFI/recovery check left
EFI unmounted; existing live policy and protected bytes were not changed.

### Assessment and next optimization target

The added pre-initialization admission layer is the strongest observed source
of overhead relative to the original direct shell path: most of this boot's
display hold preceded shell entry, and repeated integrity work is substantial
even warm. Exact cold-boot attribution and the difference from the owner's
original installation remain unmeasured; there is no paired original boot
benchmark. The evidence does not establish slower GPU execution, an IB error
or an ACPI regression as the cause of this delay. PR28's per-application wait
is not a fixed multi-second boot sleep; WindowServer remains excluded.

Prioritize phase timing and an audit of redundant admission work while
preserving complete content/identity verification, current build34 admission,
hardware waits and exact recovery. Do not infer an elapsed-time benefit from
the uninstalled 1 MiB hashing helper. No startup optimization, driver install,
GPU workload, resident monitor or power action was activated by this inquiry.
The [sanitized follow-up record](validation/build34-boot-latency-20261119.json)
contains derived values only; raw logs and profiling snapshots remain private.

## Bounded parallel-verification candidate: 2026-11-19

Following the owner's continuation, `verify_sha256_files` was added to the
existing integrity utility as an **uninstalled candidate**. It reads every
selected file in full on every invocation, using the same identity-checked
1 MiB reader. It permits one or two workers, checks exact full lowercase
SHA-256 digests, and waits for all workers before returning or raising.
There is no digest/metadata cache and no cross-phase reuse. Invalid expected
digests, read failures, observed file changes and mismatches remain errors.
The limit is per invocation, not system-wide: if adopted by both independent
startup processes, their protected-file phases could use four readers in
total. Two readers can increase simultaneous CPU demand.

An offline private adapter was derived from the exact installed validator's
source. It preserves the complete receipt/authorization/recovery prelude,
kill-switch semantics and selected-path exclusions, replacing only the serial
protected-file digest loop. Its source matcher rejects an unknown selection
loop. All surrounding policy, kernel identity, plugin, cache, historical
contract, EFI/recovery and startup-deadline checks remain unchanged. This
adapter is a read-only evaluation harness, not an authenticated installation
scope or a ready-to-run startup entrypoint.

### Correctness and read-only validation

- **21 public CPU methods** pass: the original 11 streaming-integrity checks
  plus 10 batch checks, including actual binary/chunk-boundary digests,
  two-reader concurrency/bounds, fresh reads in each phase, missing/changed
  files, malformed expectations, and joining sibling work on failure.
- **14 private CPU methods** compare the actual installed validator with the
  adapter: accepted-state and selected-path equivalence, all four receipt
  conditions, authorization/installation intent, exact kill-switch/recovery
  handling, changed/missing files, fresh phases and unknown-source refusal.
- Four complete read-only gate sequences pass, with identical derived
  contracts, unchanged live wrapper/desktop source, full EFI/recovery checks
  and no startup, GPU workload or power action. EFI was left unmounted.
- Two additional same-contract phase comparisons pass in opposite execution
  orders. Every option re-reads and verifies the selected files. Raw snapshots
  and source adapters stay private; no new runtime was installed.

### Performance result and decision

All values below are warm read-only observations, not boot measurements:

| Protected-file phase | Original whole-file serial | Streaming single reader | Streaming two readers |
| --- | ---: | ---: | ---: |
| Forward order | 2.536 s | 3.037 s | 2.043 s |
| Reverse order | 1.877 s | 3.784 s | 1.133 s |

The two-reader phase was about **19.45% and 39.65% shorter** in these paired
observations. Its process CPU time was 3.416/1.521 seconds versus the original
2.530/1.874 seconds, so lower CPU consumption is not consistently demonstrated.
The 2 MiB bound describes the two read buffers only; it is not total process
or boot memory, because other admission functions remain unchanged.

Complete sequential gate samples were mixed: original/candidate totals were
18.099/19.499 seconds in the first pair and 21.220/17.744 seconds in the
opposite-order phase-instrumented pair. The individual gate functions and
system scheduling also varied. These limited observations do not establish
an overall startup improvement or justify adding their savings to the
previous display-hold measurement.

**Do not install this candidate solely on the local phase result.** Keep the
current accepted build34/VBL/AML/plugin and startup jobs. A prospective
activation needs a fresh exact startup scope, helper/adapter hash pins,
CPU-tested entrypoints and exact job-only recovery that preserves the
accepted plugin; the historical plugin rollback must not undo that accepted
plugin for a new controller experiment. Phase-specific cold-start evidence
is required before a boot-speed acceptance claim. No optimization deployment,
startup replay, resident monitoring or reboot was performed here.

See the [sanitized candidate record](validation/build34-boot-hash-batch-20261119.json).

## Inactive phase-clock preparation: 2026-11-19

Because the parallel candidate has not demonstrated consistent whole-gate
benefit, a separate **measurement-only** scope is prepared but **not installed**.
It retains the original serial file verification. The bounded startup module,
AML selector and initialization shell are byte-identical to the accepted
installation. The owner entry adds timing enablement inside its existing
exception/recovery boundary; original calls, return values, exceptions and
deadline logic are retained.

The new original utility
[`build34_startup_phase_clock.py`](../tools/build34_startup_phase_clock.py)
records process-local monotonic start/end, elapsed and CPU intervals for fixed
labels. It records no arguments, results or exception messages. Nested records
overlap and must not be added; clock origins are not compared between processes.
Each process can collect at most 256 records in this scope; later calls still
execute every original check. A log reaching that budget must be treated as
potentially incomplete. Logging adds its own overhead, so an instrumented boot
cannot be presented as an uninstrumented speed comparison.

Private source bindings observe owner policy/build/entry, route/static,
protected-file validation, loaded identity, complete EFI/recovery checks and
bounded startup/guardian functions. The sink uses root-owned regular files,
mode 0600, no symlink following and one hard link. A logging failure cannot
mask an original validator exception. If logging fails after an otherwise
successful action, the existing entry's failure handling is used; it is not
counted as a successful measurement.

The fresh scope pins its complete source/policy/job copies and preserves the
accepted plugin scope's historical contracts and derivation. Its policy keeps
all old pins except the two *prospective* startup-job digests, and adds the new
scope's pins. Those two live jobs still contain their exact accepted original
bytes; the prospective policy is intentionally not admitted as installed yet.
No activation intent, phase log, startup bootstrap or power action exists.

The new controller's recovery can restore only the two exact saved startup
jobs, using the preserved atomic job writer. It never invokes the historical
plugin rollback. Unknown job bytes are rejected, uninstalled scopes cannot
recover, and recovery power actions are prohibited in the preparation boot.
This is controller recovery; the existing initialization shell's own failure
handling is unchanged.

**30 CPU methods pass**: 11 public timing transparency/budget/failure tests,
13 private scope-contract and temporary-directory recovery-dispatch tests,
and six root-owned temporary binding/sink tests with fake action modules.
The latter tests do not run the real startup or guardian. Preparation passed
the current installation's complete read-only admission and EFI/recovery
checks. Independent inactive readback verified the seals, unchanged actual
derived contract, exact original live jobs, prospective plist syntax and
attributes, preserved policy pins and byte-identical bounded/AML/shell inputs.
It did not run the new entry against substituted live jobs or test a boot.

Any next activation must first read back the actual new live job/policy state
before an explicitly authorized test restart. Do not bootstrap this prepared
scope in the current boot or replay old observations. After a new boot,
require fresh admission/completion receipts and independent exact runtime
readback before interpreting phase timings. Hardware acceleration, desktop
takeover, PR28 daily 250 ms/WindowServer exclusion and disabled resident
monitoring remain unchanged at this preparation.

See the [sanitized preparation record](validation/build34-boot-phase-preparation-20261119.json).

## Authorized phase-clock installation: 2026-11-19

The owner subsequently authorized this measurement-only installation and one
ordinary test restart. The two startup job files now match the previously
sealed timing-scope copies. They were changed through the preserved atomic
writer without bootstrapping startup in the installation boot. The accepted
plugin, kernel, selected cache, AML, EFI and runtime settings are unchanged.
The parallel hashing candidate remains disabled.

The actual new owner entry's `check` passed with the new live job files, and
produced 15 successful **check-only** timing records. An independent full
readback passed the exact mapped WindowServer plugin, complete 416-record
cache/29 codeless records/415 unrelated images, loaded AML, full EFI/recovery,
plugin signatures and exact recovery copies. The actual derived contract and
all previous policy entries except the intended job pins remain preserved.
The same WindowServer survived the finite observation, all four driver error
counters stayed zero, no matching report appeared, and recovery was not used.
These installation-boot `check` records are not startup measurements.

The installation added seven CPU/temp-directory methods covering exact job
replacement, consumed-scope/unknown-state refusal, partial-write readback and
same-boot job-only recovery dispatch. A fresh observer adds 15 CPU methods for
new-boot/receipt/deadline refusal, runtime progress/error checks, exact job
retirement and selecting only the new boot's startup/guardian phase logs.
Together with the existing 30 phase/scope/binding methods, **52 methods pass**.
Temporary recovery-dispatch coverage does not prove real live recovery.

The new observer is staged but remains unloaded in this boot. It requires
fresh successful receipts from this timing scope, independently verifies the
runtime and complete recovery state, collects the startup/guardian phase
records, and removes only its exact own job. Its receipt-wait/total limits
remain 360/420 seconds; it cannot submit GPU tests, recover the installation,
request power actions or retry. A separate independent readback verified all
observer pins and actual live jobs, then repeated the actual new owner check
after staging. The original 45/150/300-second startup limits are unchanged.

At this installation/pre-restart checkpoint no power command has been sent,
and cross-boot behavior remains **pending**. The authorized restart must be
requested only once and verified from new-boot evidence. Do not replay this
installation, stage a second observer, or interpret the existing roughly
90-second post-release observation as progress-bar blocking. An instrumented
restart measures phase attribution; it does not itself prove faster boot.
Keep build34/VBL/AML/render-clear, daily PR28 250 ms with WindowServer exclusion,
and disabled resident monitors. Controller recovery restores only the two
startup jobs and never rolls back the accepted plugin.

See the [sanitized installation record](validation/build34-boot-phase-installation-20261119.json).

## Phase-clock boot accepted: 2026-11-19

The single authorized restart completed. Fresh timing-scope receipts, the
finite observer and a separate independent full readback all passed on macOS
26.7.2 build 25G332. Exact live jobs, the mapped render-clear plugin, complete
416/29/415 cache metadata, loaded AML, full EFI/recovery and preserved owner
policy passed. No recovery occurred, no matching report appeared and all four
driver error counters remained zero. The same WindowServer stayed alive
within each finite observation. Both startup processes ended; the observer
deleted its exact own job and exited. No additional startup, GPU workload or
power action was executed during this follow-up.

### Measured display hold and admission

This boot's display hold was **26.677336 seconds**, versus 26.346563 seconds
in the preceding separate boot: a difference of +0.330773 seconds. This is an
instrumented, unpaired observation with no demonstrated speed improvement.
The script log starts at approximately 15:26:50 and records release at
15:26:57, leaving about 19.4–20.4 seconds of hold before script entry and about
seven seconds inside initialization before release. Its completion around
15:28:28 includes approximately 91 seconds after release, not proved
progress-bar blocking time.

The startup process produced 18 completed records and the guardian 59; neither
hit the 256-record budget. Their clocks are analyzed independently:

| Measured interval | Startup process | Guardian process |
| --- | ---: | ---: |
| Initial owner construction/admission | 6.666 s | 9.909 s |
| Initial loaded-identity check | 0.408 s | 0.459 s |
| Initial installed checks | 2.641 s | 2.727 s |
| Initial full EFI/recovery verification | 1.556 s | 2.294 s |

The startup process reached the end of its final pre-shell EFI check
**19.843049 seconds after its own recorded entry**. Its bounded-startup entry
to first installed-check interval was 8.565976 seconds, including guardian
readiness waiting plus journal, receipt and PID checks. Do not add that
interval to the table as if it were independent of guardian work. The guardian
reached its initial EFI-check end 15.405609 seconds after its own entry.
There is no cross-process raw-clock alignment or complete power-on-to-desktop
measurement here.

### Repeated work and next priorities

Across the finite startup supervision, the guardian made nine installed-check
calls totaling **66.981810 inclusive seconds**. Its ten protected-file
verification calls totaled **29.749855 seconds**, already included within
larger phases. The guardian entry took 120.492626 elapsed seconds and
50.490247 process CPU seconds; this includes the post-release supervision and
does not mean the progress bar lasted two minutes. The startup entry took
117.887082 elapsed seconds and 7.830191 process CPU seconds, largely waiting
for readiness and the original shell. Totals from these concurrent processes
must not be added into boot duration.

A separate current-owner, read-only warm `build` profile passed in
10.219649 seconds, including 823 SHA-256 calls using 5.673888 exclusive
seconds. Loaded identity and full EFI/recovery were verified afterward. This
supports the integrity-work hotspot, but does not attribute those warm-profile
seconds to the earlier cold boot or prove a GUI-stutter cause.

A small CPU-only backend screen compared the current Python's LibreSSL 2.8.3
SHA-256 with the system CommonCrypto implementation. Both produced the same
complete digest. For four repeated passes over the same 8,724,144-byte memory
buffer, the forward-order Python/native wall times were 0.064007/0.051077
seconds; reverse-order native/Python times were 0.058286/0.052966 seconds.
Results are mixed, so no native-backend replacement was prepared or installed.
This memory-only screen is neither protected-file verification nor a startup
benchmark, and does not establish a faster backend for this installation.

Priorities from this evidence are:

1. Reduce execution cost of complete admission on the guardian-readiness and
   pre-shell paths while preserving every required check and failure boundary.
2. Evaluate the complete protected-file verification phase. The earlier
   two-reader candidate remains uninstalled; its mixed whole-gate results
   still do not establish a boot-speed benefit.
3. Review finite post-release supervision overhead separately. Preserve its
   current bounded policy until a separately validated minimal change exists;
   removing its roughly 90-second observation cannot be counted as saving
   that much progress-bar time.

The new offline-only
[`analyze_build34_startup_phases.py`](../tools/analyze_build34_startup_phases.py)
validates completed single-process interval trees and subtracts immediate
children for exclusive recorded elapsed time. Twelve CPU methods and both
actual process captures pass; exclusive totals reconcile to each process's
root interval. It rejects malformed/incomplete parentage, overlapping siblings,
mixed duplicate sequences and inconsistent durations, flags a full record
budget, and omits clock origins. Exclusive time still includes uninstrumented
work and waits; inclusive totals overlap. This tool changes no startup entry
or deployed helper.

This accepts the **measurement scope's boot behavior**, not a boot-speed fix,
visual-artifact repair, physical FPS result or long-term stability. Preserve
build34/VBL/AML/render-clear, daily PR28 250 ms with WindowServer exclusion,
serial full-file checks and disabled resident monitors. Do not replay consumed
installers/observers, weaken admission or issue another reboot under the
already consumed single-restart request.

See the [sanitized boot record](validation/build34-boot-phase-boot-20261119.json).

## Startup-order candidate, offline only: 2026-11-19

A subsequent ordinary boot has now passed its own independent current-boot
readback. This is separate from the consumed phase-clock observer's earlier
boot result. The actual two live jobs, current-boot startup completion,
18 startup/59 guardian timing records, exact mapped plugin, loaded AML,
complete 416/29/415 cache metadata, full EFI/recovery and daily policy passed.
Startup supervision ended; no recovery or matching report appeared, and all
four checked driver error counters remained zero. This follow-up did not run
startup, initialize the GPU, submit a GPU test or request another restart.

### Relationship to original nullarc

The upstream startup script at the locally available pinned upstream commit
`3497d87b229e4839d8d2a03ebe9127f2a30f332b` retains the same broad sequence:
wait for the framebuffer, initialize/claim the accelerator, arm scanout and
AGDC, release the display, then observe WindowServer for 90 seconds. It also
has the separate resident hang watcher. Its `tools/phxctl` component was
reviewed under the repository's MIT/GPL-2.0-only option; no upstream code or
binary was copied for this candidate, and all license/notice files remain
unchanged. This comparison is to that pinned source, not a claim about the
latest upstream revision or an original-driver boot benchmark.

Replacing the installed entry with the whole upstream script would not isolate
the measured pre-shell admission cost, and would conflict with the owner's
disabled resident-monitor policy. Keep the accepted protected GPU shell and
hardware waits. The startup-order experiment instead targets the wrapper's
full checks that currently run after waiting for guardian readiness.

### Exact proposed order and failure boundaries

The new import-only helper,
[`build34_startup_preflight.py`](../tools/build34_startup_preflight.py), runs
the **same complete installed checks and full EFI/recovery verification once
each before waiting for readiness**, then requires the existing current-boot
receipt/age/root-PID/command validation. This can overlap work with the
already independent guardian process; it creates no reader threads, digest
cache or additional guardian, and skips no successful-path full validator.
The guardian's own code is unchanged.

Private exact-source review confirmed that the existing EFI context serializes
access through its root-owned, no-follow, exclusive lock with a 60-second
acquisition limit. It requires the selected EFI initially unmounted, mounts
read-only, verifies the entire selected manifest and recovery copies, and
unmounts in `finally`. The experiment retains that implementation. The active
phase scope's recovery changes only the two startup jobs; it never changes the
accepted plugin, kernel/cache or EFI. Extra candidate boundary checks refuse
pending startup/guardian failure, current/historical recovery, or either live
job differing from its pinned after copy. Moving checks earlier is not an
atomic snapshot against a privileged concurrent writer.

The original 45-second readiness limit starts **before** the moved checks and
is checked after them and after receipt validation, even if readiness is
already present. This is stricter than timing only the old readiness loop.
The helper does not interrupt a blocked validator: the existing EFI-lock and
outer-worker bounds remain necessary. The original final framebuffer/hold
gates, protected shell launch, completion conditions and recovery handler are
byte-for-byte unchanged by the private adapter. The 150/300-second desktop/
supervision limits and exact job-only recovery remain required for any future
scope; no current scope or sealed file was edited.

### CPU verification and adoption limit

The helper's 18 CPU methods pass. Eighteen additional private methods execute
the actual pinned `future_startup` function with CPU/temp-directory substitutes,
including source-drift refusal, unchanged shell arguments/recovery handler,
full-check counts, pending-startup refusal, stale/wrong-boot/nonroot/wrong-action
guardian rejection, timeout, live-job replacement and recovery/failure during
the wait. The unchanged framebuffer and hold gates still reject bad states.
Thirteen candidate-scope CPU/temp-directory methods cover exact sealed inputs,
two-job-only recovery, one-use/same-boot power refusal and unknown-state refusal.
Together with 44 existing integrity/clock/analyzer methods, **93 methods pass**.
These fixtures cannot prove real startup recovery or cold-boot improvement.

### Read-only warm comparison and inactive scope

Two fresh processes per trial ran the real current owner construction, loaded
identity, full installed checks and full EFI/recovery checks. The synthetic
readiness signal lived only in a new private evaluation directory; it is not
a real startup/desktop receipt. Neither `future_startup`, guardian monitoring,
the GPU shell nor a recovery function was called. One parent's clock measured
each handoff; worker clocks were not aligned or added to elapsed time.

| Trial order | Original handoff | Candidate handoff | Difference |
| --- | ---: | ---: | ---: |
| Original, then candidate | 39.592668 s | 30.230798 s | -9.361870 s |
| Candidate, then original | 37.729802 s | 25.843169 s | -11.886632 s |

Both orders favor the candidate in this warm harness. Summed worker CPU was
31.397746/31.058465 seconds in the first pair and 27.530304/26.505264 seconds
for original/candidate in the reverse pair. These CPU sums describe work,
not boot elapsed time. Construction/identity durations varied substantially,
so these four samples do not isolate the ordering effect from scheduling,
cache or other system variation. Do not promise a 9–12 second boot saving.
Each pair ended with a separate full current-runtime/cache/loaded-AML/EFI/
recovery/policy readback; both passed with no new matching report, error
increase or recovery. All evaluation processes exited.

A fresh **inactive** private scope is now sealed and independently read back.
Its 13 sealed inputs include the exact CPU-tested helper, candidate bounded
startup, unchanged owner/timing/guardian/AML/shell sources, both prospective
jobs, policy and both exact accepted timing-job recovery copies. Before/after
job attributes differ only in scope paths. The prospective runtime contract
equals the accepted current contract, and prior policy entries are retained
apart from the two prospective live-job pins. The prior timing contract is
pinned as historical evidence, rather than calling its old live-job admission
after a future transition to third-state job bytes. Source compilation and
actual adjacent-helper binding passed without executing startup.

This helper remains an **uninstalled evaluation candidate**. The actual live
jobs and policy still match the accepted timing scope; no installation intent,
new observer job or power action was created. A separately authorized live
trial must use the new exact scope, preserve its job-only recovery and obtain
fresh current-boot evidence. Never overwrite the accepted sealed timing scope or
replay its consumed installer/observer/restart authorization. Preserve
build34/VBL/AML/render-clear, PR28 daily 250 ms with WindowServer exclusion and
disabled resident monitors.

See the [sanitized evaluation record](validation/build34-startup-order-candidate-20261119.json).

## Authorized startup-order installation: 2026-11-19

The owner separately authorized installing the sealed startup-order candidate
and one ordinary test restart. The two actual startup job files now match the
candidate's exact after copies. Installation used the preserved atomic writer;
neither startup process was bootstrapped in this boot. The accepted driver,
selected cache, plugin, AML, EFI and runtime settings are unchanged.

The actual new owner entry's `check` passed and produced 15 successful
**check-only** timing records. A separate full readback of the installed route
passed the exact mapped WindowServer plugin, full 416-record cache metadata
including 29 codeless records and 415 unrelated images, loaded AML, full EFI
and recovery copies, plugin signatures and unchanged runtime contract. The
same WindowServer survived the finite observation, all four checked driver
error counters stayed zero, no matching report appeared and recovery was not
used. Startup supervision remains ended and resident monitoring stays off.

All 93 candidate/scope methods plus seven installer and 15 observer methods
pass: **115 CPU methods**. Installer coverage includes refusing a consumed
scope, another boot and unknown live jobs; a simulated partial write is read
back before dispatching exact same-boot job-only recovery. These fixtures do
not prove real live recovery or faster startup.

A new finite observer is sealed and staged for the next boot, without loading
it now. It requires a new boot, successful fresh candidate startup/desktop/
completion receipts and the exact new startup/guardian timing files. It
independently checks the full runtime/cache/loaded-AML/EFI/recovery state,
then removes only its exact own job. Its receipt-wait and total limits remain
360/420 seconds, with no GPU submission, recovery, power action, retry or
resident supervision. Independent staging readback verified the actual jobs,
observer/source/contract pins and unloaded state, then repeated the actual new
owner check. No current-boot startup or guardian action was replayed.

The original guardian implementation, complete serial hashes, hardware waits
and 150/300-second desktop/supervision limits are preserved. The candidate's
fixed 45-second readiness limit includes its moved full checks and receipt
validation. Its recovery restores only the two exact accepted timing jobs;
it cannot roll back the accepted plugin, kernel/cache, AML or EFI.

At this documented pre-restart checkpoint, no power command has been sent
and **cross-boot acceptance is pending**. Synchronize this record, request the
newly authorized ordinary restart exactly once, then read the new boot's
receipts and independently verify runtime before interpreting timings. The
four warm handoff samples remain supporting evidence only; no cold-boot
speedup, physical FPS, visual repair or long-term acceptance is claimed.
Do not ask for the same authorization again, replay the installer/observer,
overwrite a sealed scope or send a duplicate power command after uncertainty.

See the [sanitized installation record](validation/build34-startup-order-installation-20261119.json).

## Startup-order boot accepted: 2026-11-19

The single authorized ordinary restart completed on macOS 26.7.2 build 25G332.
Fresh startup-order startup, desktop and completion receipts passed the finite
observer, followed by a separate independent full readback. Both verified the
exact two installed jobs, mapped WindowServer plugin, full 416-record cache
metadata (29 codeless records and 415 unrelated images), loaded AML, full EFI
and exact recovery copies. The same WindowServer survived each finite
observation with framebuffer and GPU-completion progress; all four checked
driver error counters stayed zero and no matching report appeared. No recovery
was triggered. Both startup processes ended, and the observer removed its
exact own job and exited. Resident monitoring remains disabled.

### Observed timing

Current-boot kernel display-hold events were independently matched to this
boot before calculating their interval. The completed startup and guardian
captures contain 18 and 59 records respectively; both interval trees passed
offline analysis without errors or hitting the record budget.

| Measurement | Earlier separate timing boot | Startup-order boot |
| --- | ---: | ---: |
| Kernel display hold | 26.677336 s | 23.479593 s |
| Startup entry to initial full EFI-check end | 19.843049 s | 11.042395 s |
| Guardian initial owner construction | 9.909287 s | 9.357501 s |
| Guardian process CPU over finite startup supervision | 50.490247 s | 49.722352 s |

The display hold was **3.197743 seconds shorter in this observation**. These
are separate, unpaired boots with scheduling and cache variation; this does
not establish repeatable savings or attribute the entire difference to the
ordering change. The earlier warm 9–12-second handoff differences are still
not cold-boot savings. No complete power-on-to-desktop duration was measured.

The EFI-check row measures the same check's end relative to its own process
entry, but the candidate deliberately moves that check **before** guardian
readiness validation. It therefore does not measure the candidate's complete
pre-shell admission or prove an 8.8-second improvement in that admission.
Process clock origins were not compared across processes.

The startup process took 114.478644 elapsed seconds and 7.513571 process CPU
seconds. Guardian took 126.524672 elapsed seconds and 49.722352 process CPU
seconds, including finite supervision after display release. Its nine complete
installed-check calls took 68.268529 inclusive seconds; ten protected-file
calls took 28.159743 seconds already nested in larger phases. This repeated
verification work remains substantial. Concurrent or nested intervals must
not be added, and post-release supervision is not demonstrated progress-bar
blocking time.

### Retained installation and limits

Keep this passed startup-order installation active. The accepted build34
kernel/cache, VBL, AML, render-clear plugin, original GPU shell, complete
serial hashes, guardian/readiness/hardware gates and original 45/150/300-second
limits remain preserved. PR28 daily waiting remains enabled at 250 ms with
WindowServer excluded. Exact recovery still restores only the two accepted
timing jobs. This result supersedes the installation record's pending-boot
status; it does not change its historical pre-restart evidence.

The existing 50 integrity/clock/preflight and 12 analyzer CPU methods were
rerun successfully, and both actual completed interval trees passed. No driver,
plugin, cache, EFI, ACPI or startup-policy edit, GPU-test submission, additional
startup execution or extra power action was performed during acceptance.

This accepts the candidate's observed startup behavior. Repeatable boot-speed
improvement, physical FPS, visual-artifact repair and long-term stability remain
unaccepted. The authorized single restart is consumed; do not replay this
installer/observer or request another restart under that authorization.

See the [sanitized boot record](validation/build34-startup-order-boot-20261119.json).
