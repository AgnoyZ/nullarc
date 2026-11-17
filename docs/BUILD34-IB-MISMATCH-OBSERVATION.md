# Original34 IB mismatch observation

This diagnostic addresses a missing fact in the unresolved original34
single-IB trigger: earlier failures reported only the first mismatching byte,
`0x2010`, actual `0xde` instead of `0xdf`. They did not establish whether the
remaining output matched the previous pattern, retained poison, was partly
updated, or accompanied changes elsewhere in the arena. The separately
[verified explicit-tail Vulkan compute workaround](BUILD34-RADV-RUNTIME-PROBE.md#complete-runtime-hardware-result)
does not answer that question or repair the unchanged native single-IB path.

## Change and interpretation

The original preamble probe gains one header and one reporting call, reached
only after positive native retirement and an observed arena mismatch. The
existing first-mismatch message and failure/HOLD remain. Removing that include
and call makes its source byte-identical to checkpoint `a4156e5`. No staged
shader/IB bytes, descriptors, resource layout, wait budgets, successful path,
kernel, ABI, production helper, A1/A2/corrected-A3 or default policy changes.

The reporter snapshots all 16 KiB through volatile CPU reads, compares it
with the same expected arena, and emits only aggregate counts. It separates
the shader page, command page, 1-KiB output and remaining guards. Each of the
256 output words is classified exclusively as current, previous-pass,
current poison, or other. Previous-pass classification is enabled only for
the second pass. The report also records whether it reobserved the original
bad byte and how many snapshot bytes differed on a second immediate read.
It prints no addresses, raw arena, shader code or firmware contents.

This adds no GPU call, wait, sleep, cache flush, initialization, retry, cleanup
or extra executing client. On failure original34's existing HOLD retains the
process and resources until independent recovery. Never terminate that held
native process. The reads happen after the failure, not before either submit.

Even a stable snapshot containing 256 previous-pattern words would describe
the CPU-visible result only. It would not prove that CP fetched an old IB,
identify a cache or disprove an ordering/visibility fault. A changing snapshot
must be reported as such rather than collapsed into a stale-pattern claim.
The observation is intended to choose a later discriminating experiment;
its counter values are not a driver-fix or performance acceptance criterion.

## Offline checks and preparation

```sh
nice -n 15 taskpolicy -b python3 -B -m unittest discover \
  -s tests -p test_upstream34_ib_preamble_runner.py -v
nice -n 15 taskpolicy -b python3 -B tools/test_upstream34_ib_preamble.py \
  --out build/ib-mismatch-observation-cpu-private
nice -n 15 taskpolicy -b python3 -B tools/upstream34_layout/ib_preamble.py \
  build/ib-mismatch-observation-native-private --compile
```

Use fresh ignored outputs. The actual probe runs under fake IOKit/CF and
ASan/UBSan in CPU checks, including every existing fault, all four policies
and both canonical halves. The fixture injects whole previous-pattern output,
whole poison and a four-way mixture to check exact counts, in addition to
individual shader/IB/output/guard corruption. A positive wait with no injected
output is checked as all poison. No ISA/cache or coherency model is used.
The runner rejects missing, inaccurate, duplicated or mistyped summaries,
and checks input hashes before and after execution. Native preparation only
compiles, signs and verifies; it never runs the binary or arms hardware.

On 2026-11-17 the final run passed nine parser unit tests and 9,136 actual
program scenarios: 1,142 cases for each of four policies in both canonical
halves, with 80 separate-process equivalence checks. Native x86_64 preparation
and signature verification passed without running the binary. An earlier CPU
run correctly classified all poison after a positive fake wait that injected
no output; the independent expected-summary oracle had omitted that existing
case. The oracle was corrected before the final pass, with no native/GPU run.
See the [sanitized offline record](validation/build34-ib-mismatch-observation-offline-20261117.json).

## New hardware boundary

A new single-use scope is required; none of the earlier single/tail/Vulkan
scopes may be replayed. Retain the exact original34 image, one initialization,
one inline-admitted executing client, at most two native submissions, positive
retirement, independent deadline and one recovery reboot. An additional
`--check` client is prohibited. Start with `--run-single`; preserve both normal
wait accounting and the complete mismatch summary before recovering. A passed
single-IB control instead changes the reproducibility finding and must not
be called a fix or followed automatically by another policy.

After recovery, independently verify GPU-off/firmware framebuffer, protected
files/links, EFI/security/kernel collections and matching diagnostic reports,
then retire the consumed job. Keep raw logs private and publish only the
sanitized observation. Graphics, desktop, default waits and FPS remain HOLD.

## Hardware observation and controller failure

On 2026-11-17, a fresh scope ran the signed source-`0afcd11` observer against
the exact original34 image on macOS 26.7.2 (`25G332`). The first dispatch
passed all 16 KiB. The second again reported `0x2010`, actual `0xde` instead
of `0xdf`, after its zero-budget wait reported native retirement.

The complete post-failure summary classified **all 256 output words as the
previous pattern**: zero current, poison or other words. There were 256
mismatching bytes, all within the 1-KiB output; each changed pattern word
differs by one byte. Shader, command-page and guard mismatch counts were
zero. The first mismatch was reobserved, and no bytes changed between the
snapshot and the second immediate read. These counts establish a stable
CPU-visible previous result at observation time. They do not establish that
CP fetched an old IB, distinguish stale command/state/data visibility, or
exclude a later update. No delayed sample or extra GPU call was performed.

The native process retained its connection and mappings in HOLD. The
controller subsequently failed its post-probe admission assertion combining
service count, build34 identity and absence of children. The available
failure record does not identify which operand failed. Consequently the
controller wrote a failure receipt, **not** a completed hardware-result
receipt; this scope is not counted as a successful trial or fix acceptance.
After recovery, an independent parser checked the complete native wait,
mismatch, summary and HOLD records. This supplemental log observation does
not replace the controller's failed outcome.

One recovery reboot returned to GPU-off with the firmware framebuffer. An
independent verifier checked the original image, 46 protected files, two
links, 347 EFI files (including 148 Microsoft files), unchanged security and
kernel collections, and no new matching diagnostic report. It then removed
the consumed job. No held process was killed, no scope was replayed, and no
driver or runtime was deployed. See the
[sanitized hardware record](validation/build34-ib-mismatch-observation-hardware-20261117.json).

The next experiment must preserve the separate failed-controller and parsed
observation outcomes. In particular, an intentionally held client cannot be
treated as if it had already completed cleanup; any revised observation
controller needs its own host checks and fresh scope. The unchanged single-IB
fault remains unresolved, and the separately verified explicit-tail compute
workaround retains its existing limited scope.
