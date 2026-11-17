# Original34 post-failure delayed IB observation

The [immediate mismatch observation](BUILD34-IB-MISMATCH-OBSERVATION.md#hardware-observation-and-controller-failure)
found 256 previous-pattern output words after native retirement, stable across
two immediate CPU reads. It did not test whether the result changed later.
The original single-IB fault remains unresolved. This new diagnostic asks only
whether the CPU-visible arena changes after one requested 100-ms delay.

## Scope and interpretation

`--run-single-observe-late` follows the existing `--run-single` path through
the first observed arena failure. It submits the same commands and descriptor,
uses the same output poison, native waits and 250-ms inter-pass pause, and
performs the same initial mismatch summary. Only after that failure does it:

1. Measure one `usleep(100000)` with the already validated monotonic timebase.
2. Report the requested delay, sleep status, clock validity and elapsed time.
3. Repeat the same full-arena read-only aggregate summary once.
4. Return failure and retain the connection/mappings in HOLD.

There is no extra GPU call, WAITSEQ, cache operation, retry, CPU arena write or
cleanup. A late all-current result still fails and holds; it is evidence for
investigating completion/visibility ordering, never a delay-based fix. A
stable previous result after the delay still does not identify an old CP
fetch or exclude a cache, state or visibility fault. A mixed or changing
result must retain its actual counts. A failed/interrupted sleep or invalid
clock prevents interpreting the requested interval as observed.

Without this explicit option, the four existing policies retain their prior
behavior. Even with the option, a successful two-pass execution has no added
sleep or observation and is only a changed reproducibility finding. No test
may automatically advance to another policy. This is diagnostic-only tooling;
original34 kernel/helper/ABI, A1/A2/corrected-A3, Mesa transport, default waits,
desktop HOLD and FPS status are unchanged.

## Offline verification

```sh
nice -n 15 taskpolicy -b python3 -B -m unittest discover \
  -s tests -p test_upstream34_ib_preamble_runner.py -v
nice -n 15 taskpolicy -b python3 -B tools/test_upstream34_ib_preamble.py \
  --out build/ib-late-observation-cpu-private
nice -n 15 taskpolicy -b python3 -B tools/upstream34_layout/ib_preamble.py \
  build/ib-late-observation-native-private --compile
```

On 2026-11-17 all 11 parser regression methods and 11,460 actual-program
ASan/UBSan cases passed: 1,146 cases across five policies and both canonical
VA halves, with 140 separate-process equivalence checks. Injected delayed
all-current and half-current results still fail/HOLD, and interrupted sleep,
backward clock, missing/malformed records and unwanted cleanup are checked.
The mock uses fake IOKit/CF, synthetic time and injected bytes; it models no
GPU cache, ISA or coherency. Native x86_64 compilation, signing and signature
checks passed without executing the native binary. See the
[sanitized offline record](validation/build34-ib-late-observation-offline-20261117.json).

## Fresh hardware boundary

No hardware scope is armed by source preparation. A subsequent authorized
scope must be fresh, use the exact original34 image and pin the source, signed
binary and recovery controller. Retain one initialization, one inline-admitted
executing client, at most two native submits, an independent deadline, no extra
`--check` client, and one recovery reboot. Preserve all native wait rows, both
summaries, timing and HOLD before recovery; never kill a held native process.

The prior scope's post-probe assertion failure is not a successful trial.
A new controller must save parsed native observations before checking any
post-trial conditions. Admission before GPU work remains strict. Once a
mismatching client intentionally holds its resources, immediately recover
after the complete observation rather than requiring that client to have
already disappeared. Independent post-reboot verification must still require
no native clients, exact build34, GPU-off/firmware framebuffer, unchanged
protected files/EFI/security/kernel collections and no new matching report.
Then remove the consumed job. No scope may be replayed. Rollback is the
existing independent GPU-off recovery; no runtime or driver is installed.

## Hardware observation

On 2026-11-17 a new source-`d1b1ab2` scope used the exact original34 image on
macOS 26.7.2 (`25G332`). One initialization and one client submitted two
single-IB dispatches. The first passed all 16 KiB. The second again failed at
`0x2010`, actual `0xde` rather than `0xdf`, after a zero-budget native wait
reported retirement. The initial summary had 256 previous-pattern output
words, zero current/poison/other words, and 256 mismatching output bytes.

The single requested 100-ms delay succeeded; its measured interval was
**101,636,975 ns**. The subsequent summary was identical: all 256 output
words still matched the previous pattern, with no shader, command-page or
guard mismatch and no byte change across either summary's immediate read
pair. Thus this trial did not observe a late correction within that interval.
It does not establish a CP-fetch/cache root cause or rule out every possible
completion/visibility fault. Increasing a wait or hiding the original
failure is not an accepted fix.

The original failure and HOLD were retained. The controller first saved the
parsed observation, then performed recovery-only identity/protection checks
while the client was still held. It did not admit further GPU work. Both
the observation controller and the independent post-recovery verifier
completed; this means the **observation** completed, not that the failing
GPU result passed. Twenty CPU controller tests had checked that distinction,
incomplete/timing-error transcripts, live witness requirements, no retries,
one recovery dispatch and retained resources.

One recovery reboot returned to GPU-off/firmware framebuffer. Independent
verification required no native clients and checked the exact original image,
46 protected files, two links, 347 EFI files (148 Microsoft), unchanged
security/kernel collections and no new matching diagnostic report, then
removed the consumed job. No driver/runtime was installed and no held native
process was killed. See the [sanitized hardware record](validation/build34-ib-late-observation-hardware-20261117.json).

The unchanged native single-IB fault remains unresolved. The separately
verified explicit-tail compute workaround retains its limited scope;
graphics, desktop, default waits and FPS remain HOLD.
