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
