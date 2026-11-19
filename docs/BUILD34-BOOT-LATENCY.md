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
