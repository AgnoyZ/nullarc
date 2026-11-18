# Build34 startup latency investigation

On 2026-11-18 the owner identified the slow phase as the Apple logo/progress
bar after selecting macOS in OpenCore. The accepted installation runs macOS
26.7.2 build 25G332, with runtime source
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496` on the default build34 branch.

## Observations

The current boot's unified log records the framebuffer display hold from
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

## Next baseline and rollback

**The candidate is prepared, not installed.** This investigation changed no
live owner entry, policy, startup job, EFI, kernel or plugin. Acceleration and
desktop takeover stay active, daily PR28 waiting stays enabled, and resident
monitoring stays disabled. No startup job, GPU workload or power action ran.

The separately withdrawn S5 candidate remains in this boot's memory pending
the owner's ordinary restart. First verify original ACPI loading and startup
timing after that restart; do not combine it with a new performance treatment
and attribute the result solely to hashing. See the
[ACPI rollback record](BUILD34-ACPI-S5-CANDIDATE.md).

Only then consider guarded helper activation, with fresh exact-identity
checks, saved wrapper/policy and the new helper pin. Never replay a startup
job or bring-up in the running boot, shorten hardware waits or weaken gates.
A future rollback must match the exact installed candidate, restore only the
saved wrapper/policy and remove only the exact added helper. With no activation
performed, leaving current owner files intact is the current rollback state.
A later manual boot comparison is required for any boot-speed claim.
