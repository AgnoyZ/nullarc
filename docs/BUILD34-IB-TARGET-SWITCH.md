# Original34 single-IB output-target comparison

The [delayed observation](BUILD34-IB-LATE-OBSERVATION.md#hardware-observation)
still found all 256 previous-pattern words after a measured 101.637 ms. It
did not distinguish an old destination/parameter combination from a new
destination carrying old parameters or missing CPU-visible writes. The
native single-IB fault remains unresolved. This diagnostic records those
CPU-visible distinctions without claiming a CP-fetch or cache root cause.

## Controlled change

Two explicit modes share the original 16-KiB BO, shader, same-address dispatch
IB at `0x1000`, two patterns, native wait budgets and 250-ms inter-pass pause:

| Mode | First dispatch | Second dispatch |
| --- | --- | --- |
| `--run-target-control` | A at BO offset `0x2010` | A at `0x2010` |
| `--run-target-switch` | A at BO offset `0x2010` | B at `0x2810` |

A and B are disjoint 1-KiB regions in the same BO. Before **each** submission,
both modes poison **both** regions with the complement of that pass's pattern.
Only the selected region is expected to change; the other must remain poison.
The whole 16 KiB is checked, including shader, command page, both regions and
all guards. The unused prewritten IB slot at `0x1200` remains the canonical
second-pattern-to-A packet in both modes. The NOP at `0x1400` is staged but
never submitted. Both submits carry one descriptor for the same 320-byte IB.

The first staged arena is identical in both modes. The second staged arenas
differ only in the rewritten IB's destination address. Expected bytes also
differ because the selected output region changes. No extra GPU command,
descriptor, WAITSEQ, cache operation, fence or delay is added. The original
five policies keep their existing arena and observation behavior. This
comparison changes CPU staging relative to the older single-region fixture,
so it needs a fresh same-binary control; old reproductions are insufficient.

After each positively retired dispatch, `IB-TARGET-SUMMARY` reports full-arena
mismatch counts and separate A/B counts for current, previous, poison and
other words, plus words matching the region's expected state. In pass zero,
current and previous patterns are identical and are counted as current.
One snapshot is compared with a second immediate volatile read. A mismatch
in the original scan, snapshot or second read fails and retains resources
for recovery. A later matching snapshot never converts a failed scan to PASS.
The summary prints fixed region identities and counts, no runtime addresses
or raw arena contents. These extra reads may affect reproducibility equally
in the two modes; the fresh control remains mandatory.

## Interpretation and sequencing

For the second switched dispatch, possible observations include:

| A | B | Limited observation |
| --- | --- | --- |
| previous pattern | poison | old destination/parameter combination is CPU-visible |
| poison | previous pattern | new destination with previous pattern is CPU-visible |
| poison | poison | neither expected output write is CPU-visible |
| current pattern | poison | current pattern is visible at the old destination |
| poison | current pattern | expected switched output, subject to full-arena checks |

Mixed values, unexpected words and changes across reads retain their actual
counts. None of these outcomes alone proves what CP fetched or excludes
cache/state/visibility faults. A passing switched diagnostic is not a native
single-IB repair or graphics, desktop, wait-policy or FPS acceptance.

First run only a fresh target-control scope. It must reproduce the precise
second-pass `0x2010` `0xde`/`0xdf` failure and independently recover and retire
before considering a **separate** target-switch scope using the same signed
binary. If control passes, fails differently, has incomplete observations or
fails recovery verification, stop the comparison. Do not automatically try
another mode, reuse a consumed scope or treat a diagnostic failure as success.

## Offline checks and hardware boundary

The actual probe is tested with fake IOKit/CF, synthetic time and injected
bytes under ASan/UBSan in both canonical VA halves. Tests check the complete
staged arena against a separately written packet recipe. In addition to the
five existing policies, both new modes cover every byte in both output
regions, boundary guards, old/new destination and pattern combinations,
absent writes, partial output and existing transport/admission faults. The
Python result oracle derives expected counts independently from injected
bytes and rejects missing, malformed or mislabeled records and false PASS.
These are CPU behavior checks, not GPU execution or coherency simulation.

On 2026-11-17, 15 parser regression methods and 32,488 actual-program
ASan/UBSan cases passed, including 216 separate-process equivalence checks.
Each original mode has 1,146 cases per VA half; each target mode has 5,257.
All 11,460 original-mode transcripts also matched the prior compiled fixture
byte for byte after excluding CLI usage lines that list the two new options.
Native x86_64 compilation, signing, signature and architecture checks passed
without executing the native binary. See the
[sanitized offline record](validation/build34-ib-target-switch-offline-20261117.json).

```sh
nice -n 15 /usr/sbin/taskpolicy -b python3 -B -m unittest discover \
  -s tests -p test_upstream34_ib_preamble_runner.py -v
nice -n 15 /usr/sbin/taskpolicy -b python3 -B tools/test_upstream34_ib_preamble.py \
  --out build/ib-target-switch-cpu-private
nice -n 15 /usr/sbin/taskpolicy -b python3 -B tools/upstream34_layout/ib_preamble.py \
  build/ib-target-switch-native-private --compile
```

Preparation does not run the native binary, install/load a driver, arm a job
or authorize GPU work. A subsequent authorized hardware scope must pin the
original34 image, source, signed binary and independently checked controller;
allow one initialization, one inline-admitted execution client, at most two
native submits, an independent deadline and at most one recovery reboot.
Save all native waits, summaries and any original failure/HOLD before
recovery. Never kill a held native process: build34 has no close quarantine.
Recovery must return to GPU-off/firmware framebuffer, independently verify
protected files/links, EFI, security/kernel collections and diagnostic-report
state, and remove the consumed job. No extra `--check` client or retry is
permitted. Rollback is the existing independent GPU-off recovery; no runtime
or driver is installed by this diagnostic.

The kernel, ABI, production helper, A1/A2/corrected-A3 and hardware-tested Mesa
transport remain unchanged. Default waits, accelerated desktop and FPS stay
HOLD. Build41/build42 remain withdrawn. No new hardware result is claimed by
this preparation.

## Fresh hardware control

On 2026-11-17, a new source-`5a5be4f` target-control scope used the exact
original34 image on macOS 26.7.2 (`25G332`). One initialization and one native
execution client submitted two single-IB dispatches. The first passed the
whole 16 KiB, with 256 current words in A and 256 poison words in B. The
second precisely reproduced `0x2010`, actual `0xde` rather than `0xdf`, after
a zero-budget WAITSEQ reported retirement. All 256 A words matched the
previous pattern; all 256 B words remained poison. There were 256 mismatching
A bytes and no shader, command-page, B or guard mismatch. Neither summary
observed changes across its two immediate reads.

The original GPU failure and held resources were preserved. Observation
collection completed, followed by one recovery reboot. Independent
verification returned to GPU-off/firmware framebuffer with no native clients,
checked the exact image, 46 protected files, two links, 347 EFI files (148
Microsoft), unchanged security/kernel collections and no new matching
diagnostic report, then removed the consumed job. The controller's 20 CPU
tests covered retained resources, no retries, independent witnesses and
saving observation before a postcheck failure. No driver/runtime was
installed or held process killed. See the
[sanitized control record](validation/build34-ib-target-control-hardware-20261117.json).

This satisfies only the fresh control/recovery prerequisite for considering
a separate same-binary target-switch scope. It is not successful GPU output
or a fix. The switched policy has not yet been executed by this record, and
all native single-IB, desktop/default-wait and FPS HOLDs remain.

## Separate hardware target switch

After that control had independently recovered and retired, a new
source-`ffafd1f` scope used the **same signed binary and result parser** on
the same exact original34 image and macOS build. No diagnostic source or
native wait policy changed. One initialization and one execution client
again submitted two single-IB dispatches. The first passed the whole arena.

The second command targeted B, with both regions first poisoned. Native
WAITSEQ initially reported busy with zero budget, then retirement with the
50,000-ns budget. The whole-arena check failed first at A's `0x2010`: actual
`0xde`, expected poison byte `0x20`. A contained **256 previous-pattern
words**; B contained **256 poison words**, with no current or unexpected
words in either region. All 1,024 bytes in each region differed from its
expected state, totaling 2,048 mismatch bytes. Shader, command-page and guard
counts were zero, as was the change count across immediate reads.

Thus this bounded comparison observed the **old destination and old pattern
combination**, rather than a previous pattern at the new destination. Since
both regions were re-poisoned before submission, A's previous-pattern words
were not the expected untouched CPU contents. This narrows the investigation
toward command/state reuse or stale GPU-visible work; it still does not prove
what CP fetched, identify a cache, or exclude a visibility fault. In
particular, a CPU-visible command page matching its expected bytes does not
establish GPU-visible command freshness. The original native fault is not
repaired.

The original failure/HOLD was retained. Observation collection, one recovery
reboot and independent retirement completed. Verification again required
GPU-off/firmware framebuffer with no native clients, the exact original
image, 46 protected files, two links, 347 EFI files (148 Microsoft), unchanged
security/kernel collections and no new matching diagnostic report. No
driver/runtime was installed, held native process killed or extra GPU mode
run. See the [sanitized treatment record](validation/build34-ib-target-switch-hardware-20261117.json).
Neither consumed scope may be replayed. All original single-IB,
desktop/default-wait and FPS HOLDs remain.
