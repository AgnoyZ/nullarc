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
