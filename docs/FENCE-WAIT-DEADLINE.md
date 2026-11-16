# Fence wait elapsed-time correction

Status on 2026-11-16: **downstream build40 remains an offline candidate**.
A separate minimal build34 backport was boot-tested and failed its native output
integrity gate; it is **not accepted or promoted to the default branch**. See
[the build34 trial below](#separate-build34-backport-hardware-trial).
An identical-probe original build34 control subsequently reproduced the same
second-dispatch failure; neither result establishes its cause or accepts the
wait candidate.
A later logging-only build34 diagnostic captured pass 1's first output byte:
actual `0xde`, expected `0xdf`. It matches pass 0's expected first byte, but
does not establish stale-cache, stale-command or fence-ordering causation. See
[the byte diagnostic below](#original-build34-byte-diagnostic).
The subsequent two-policy diagnostic reproduced that failure with a rewritten
IB, while its separate fresh-IB trial passed two complete guarded dispatches.
This prioritizes the rewritten/reused-IB path for investigation; it does not
pass the wait candidate's separate hardware gate. See
[the paired comparison](NATIVE-IB-FRESHNESS-DIAGNOSTIC.md#original-build34-fresh-comparison).
The cumulative A1/A2/A3 native-desktop candidate remains on HOLD after the
post-gate WindowServer watchdog. This change does not establish the cause of
that hang or demonstrate a frame-rate or interactive-latency improvement.

## Trigger and scope

The corrected A3 trial on macOS 26.7.2 / 25G332 passed a bounded short test,
then the user reported mouse and GUI stutter during background work. At
2026-11-16 13:41:42.7421 +08:00, WindowServer's main thread had not checked in
for 40 seconds. Exact-image symbolication placed its execution queue inside
the RADV `acd_kext_wait_seq` / IOKit call while its main thread waited for
command-buffer scheduling. A second graphical process was also waiting in
RADV. These stacks identify a blocking path, not the GPU command, resource
hazard or individual A1/A2/A3 change responsible.

The source of this evidence is the separate candidate branch
`backport/upstream34-a1-a3`, commit
`6f593b54457ceba5a378e88f2279eeadac4c9390`, files
`docs/UPSTREAM34-BACKPORT.md` and
`docs/validation/upstream34-backport-post-gate-watchdog-20261116.json`.
Raw diagnostics, image identifiers, addresses and personal paths remain local.

The initial offline correction was developed on `downstream/780m-tahoe`, starting at
`81bd11df4ffd775985a4ad40727f7a1f349b7365`. It does not replace the candidate's
baseline bring-up component or change the then-default branch
`upstream34/vram-layout-fix` at
`90bb06f6f9255cb5a16cc5eb87e78032566b2000`. The downstream kernel build marker
advances from 39 to 40 so future source/binary identification distinguishes it.
That offline build did not change the installed build34 or GPU-off startup state.
The subsequent default-branch A1/A2/corrected-A3 transfer and the separate build34
wait backport trial are distinguished below.

## Proven defect and narrow correction

`IOAccelPhxNativeClient::doWaitSeq` previously accumulated the requested
`IODelay(50)` / `IOSleep(1)` durations. Time spent descheduled, oversleeping or
waiting for the GPU lock was omitted. Thus a nominal timeout, including the
two-second `PHXN_WAIT_CAP_NS`, could cause repeated waits after its real-time
budget had already expired.

The method now captures `mach_absolute_time()` before the first retirement
observation and converts the elapsed tick difference with
`absolutetime_to_nanoseconds()` before deciding whether to delay again. The
existing 50-us polling phase below one millisecond and one-ms yielding phase
afterward use actual elapsed time. An already observed completed fence still
wins, including a completion observed on a delayed wakeup.

This is not a hard real-time deadline: a single scheduler delay, GPU-lock
acquisition or retirement observation can still exceed the budget. The change
prevents further polling delays after that overrun is observed; it cannot
cancel a blocked lock acquisition or repair GPU execution.

No ABI or timeout cap changes. Target validation, emitted/retired outputs,
closed-client checks, hardware-disappearance refusal, pending fences, cache
maintenance and ownership/reclamation conditions are unchanged. A timeout
does not fabricate fence completion, release BOs, unpin host memory or disable
the backend. The plugin's longer outer wait policy is unchanged and remains a
separate unresolved issue; simply shortening it could expose in-flight resource
lifetime hazards.

## Regression method

The existing context-retirement harness extracts and executes the actual
kernel method bodies with ASan/UBSan. The host clock has a nonzero epoch and
10-ns ticks, so using raw ticks as nanoseconds or treating an absolute timestamp
as a duration fails the same timing assertions. OS delay, sleep and GPU-lock
fakes can independently consume more virtual elapsed time than requested.
These are deterministic host tests and execute no GPU commands.

Eight new cases cover zero/short timeouts, delay and sleep overshoot, the capped
timeout, preemption while polling, already-complete work at zero timeout, and
completion after an oversleep. They also check that incomplete work retains its
BO container and descriptors without a host `complete()` call. Existing
close-during-wait, wait-after-close and context/queue-retirement cases remain.

Before the production edit, the expanded 123-case harness passed 119 cases and
failed exactly these four assertions against the original method:

| Case | Requested timeout | Injected delay | Required corrected behavior |
| --- | --- | --- | --- |
| `wait-delay-overshoot` | 3 ms | First 50-us delay takes 3.5 ms | One delay, no sleep; report pending |
| `wait-sleep-overshoot` | 3 ms | One-ms sleep takes 100 ms | 20 short polls, one sleep; report pending |
| `wait-cap-overshoot` | Maximum integer, capped to 2 s | One-ms sleep takes 3 s | 20 short polls, one sleep; report pending |
| `wait-poll-preemption` | 3 ms | Initial retirement lock consumes 4 ms | No delay or sleep; report pending |

The original method SHA-256 was
`d88845abb598658632a9c7f31d9d3df61ab6fed60a6515a250181366a234f87c`.
The first harness draft had two additional failures because its completion
expectation did not match the fixture's global sequence; correcting that test
fixture before editing production code left exactly the four failures above.
An initial committed-source check also exposed the runner contract's fixed
case-list index. It now checks the full list with named exceptions for legacy
default-branch cases, so inserting a case cannot shift that boundary again.
Committed-source validation at `688e0cee0bbda3516e2de1f9ef38c4e9e3da572f` passed:

- 729 Python source/runner tests, plus the focused six-test runner contract.
- 123 context/wait, 82 BO, 86 queue-retirement and 71 VM-binding
  ASan/UBSan cases: 362 actual-method scenarios in total.
- Native build40 kernel compilation/linking against the pinned SDK. Three
  shadow warnings are in unchanged queue adoption/submission code.
- `git diff --check`, exact case sets and source/method/harness hash binding.

Source-bound results and the interrupted earlier check are recorded in
`validation/fence-wait-deadline-20261116.json`. Its build40 GPU/hardware flags
remain false. The passing rerun supersedes the earlier runner-contract failure.

## Separate build34 backport hardware trial

The default branch subsequently advanced to
`64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`, carrying A1/A2/corrected-A3.
Its kernel still excludes this wait correction. A detached, uncommitted candidate
changed only the build34 `doWaitSeq` delay accounting, retaining build34 and ABI
1.12. The older baseline's ownership and locking behavior was preserved rather
than replaced with the downstream build40 implementation. Its actual-method
ASan/UBSan harness passed nine cases and reproduced four original timing failures;
the native kernel build passed. These are host/build results, not hardware
acceptance.

The owner authorized a temporary OpenCore kext replacement and a bounded headless
boot trial on macOS 26.7.2 / 25G332. The candidate's exact loaded image and geometry
were admitted, and the original complete EFI manifest was restored **before GPU
initialization**. The original compute/graphics tests and both queue adoptions
passed. The native probe then submitted two shader dispatches. The first verified
all 16 KiB of code, command, output and guard bytes. After the second fence was
reported complete, its first output byte at BO-relative offset `0x2010` did not
match the expected value. The probe did not record the actual/expected bytes, so
this evidence cannot identify stale cache contents or the incorrect value.

Three wait calls were observed: a completed zero-budget wait, a pending
zero-budget wait, and a completed 50-microsecond-budget wait. Their elapsed times
were 3,717 ns, 5,179 ns and 15,619 ns. The two-second cap path was not reached.
The data mismatch prevents accepting the planned 96-dispatch gate; neither the
two-client phase nor the background CPU workers started. A completed fence alone
is not sufficient evidence of correct GPU output or improved GUI responsiveness.

The failed probe retained its connection and mappings until the single recovery
reboot. The 35-second process timeout came from this intentional HOLD, not a
35-second wait call. The coordinator and independent witness also raced to create
the exclusive recovery intent; one received `FileExistsError`, while exactly one
recovery was dispatched. Subsequent offline control tests verify immediate HOLD
reporting and serialized recovery: six competing processes produce one mocked
EFI verification and one mocked shutdown dispatch. No GPU or reboot was used in
those fixtures. The consumed trial packet was preserved unchanged.

Independent recovery checks verified the original build34 image, all 347 baseline
EFI files, 148 Microsoft files, OpenCore configuration, 46 protected files, two
library links and security settings. No new matching diagnostic report was found.
The consumed launch job was removed. GPU-off and the firmware framebuffer remain;
the wait backport stays out of the default branch. A1/A2/corrected-A3 source
migration is retained, with the previous accelerated-desktop HOLD unchanged.

Sanitized source/image hashes and exact observations from this candidate trial
remain in [the build34 failure record](validation/upstream34-fence-wait-20261116.json).
That historical record predates the separate original34 control below; it has not
been relabeled as a passing candidate result.

## Original build34 control

On 2026-11-16 the owner authorized one current-boot initialization/adoption of
the already loaded original build34, the **identical frozen probe executable**,
and at most one recovery reboot. There was no preliminary reboot, EFI/kext
replacement, desktop takeover, tuning write, CPU load or concurrent GPU client.
Independent admission verified the original image, ABI 1.12, target geometry,
firmware framebuffer and startup containment before initialization.

The original compute/graphics checks and both queue adoptions passed. The native
probe again verified all 16 KiB on pass 0, then reported positive retirement but
an output mismatch at `0x2010` on pass 1. Two dispatches were submitted; one was
fully verified. Four wait observations were captured:

| Pass (zero based) | Budget | Pending | Elapsed |
| --- | --- | --- | --- |
| 0 | 0 ns | yes | 5,560 ns |
| 0 | 50,000 ns | no | 15,549 ns |
| 1 | 0 ns | yes | 7,635 ns |
| 1 | 50,000 ns | no | 12,904 ns |

The two-second cap path was not reached. After initializer/client registration,
read-only values of `debug.phxbos_flush`, `debug.phxbos_flush_bytes` and
`debug.phx_hang_kills` were all zero. These were captured **before** the native
probe, not during or after its failing submission. Their values alone do not
prove a cache or hang-recovery cause. Source inspection also shows an
`ACQUIRE_MEM` cache synchronization packet in the shared shader command builder
and a kernel `RELEASE_MEM` completion packet; their presence does not certify
hardware visibility or ordering.

The corrected monitor detected the explicit FAIL/HOLD immediately, retained the
probe's connection/mappings and dispatched one serialized recovery. The startup
observer recorded the original image and performed no GPU retry. Independent
post-recovery verification confirmed all 347 EFI files, 148 Microsoft files,
OpenCore configuration, 46 protected files, two library links and security/kernel
collections unchanged, with no new matching diagnostic report. The consumed job
was removed. GPU-off and the firmware framebuffer remain.

This establishes that the observed failure is **not exclusive to the wait
correction**. It does not identify whether the probe, repeated-buffer visibility,
GPU execution or fence/data ordering is responsible, and does not pass the
candidate's separate 96-dispatch acceptance gate. The wait backport remains
isolated; default stays at `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c` with
A1/A2/corrected-A3 retained and accelerated-desktop HOLD unchanged.
See [the original34 control record](validation/upstream34-fence-wait-baseline-20261116.json).

Both frozen hardware probes logged only the first mismatching offset, not the
actual/expected bytes. The repository probe now records the zero-based pass and
the **single observed byte used in the failing comparison**, plus its expected
byte. This is a failure-log change only: packet generation, data patterns,
submission count, waits, full-byte verification and cleanup are unchanged. It
does not modify or retroactively enrich either frozen hardware trial. Host fault
injection checks the exact diagnostic for shader, IB, output and guard corruption
in both VA variants. Any new hardware diagnostic trial must preserve build34's
failure HOLD; the repository probe's normal close path is not a safe substitute
for that adapter on this older kernel.
The passing clean-snapshot checks comprise nine focused Python tests, 1,970
actual-C++ ASan/UBSan simulations and native compilation of both the repository
probe and a private build34 HOLD adapter. Neither compiled native binary was
executed during that host validation. The separate authorized adapter trial
below subsequently failed the output gate. Source hashes and host-validation limits are in
[the diagnostic validation record](validation/native-shader-mismatch-diagnostics-20261116.json).

Cache visibility, buffer reuse and fence/data ordering remain investigation
leads. Do not bypass the integrity check, globally enable costly cache flushing,
or claim a frame-rate/stability fix. Raw diagnostics, image identifiers,
firmware, EFI and binaries remain private.

## Original build34 byte diagnostic

The owner separately authorized one current-boot original34 initialization,
the logging-enhanced single-client HOLD adapter with a maximum of 32 dispatches,
and at most one recovery. No EFI/kext replacement, preliminary reboot, desktop
takeover, tuning, CPU workers or concurrent-client phase was performed. Exact
original build34 and probe hashes were independently admitted on macOS
26.7.2 / 25G332. The sole probe-source delta from the prior frozen control is
the single-read mismatch log described above; its packet builder, buffer layout,
patterns, waits, 250-ms inter-dispatch pause and failure HOLD are unchanged.

Original compute/graphics outputs and both queue adoptions passed. Pass 0
verified all 16 KiB. Pass 1 reported positive retirement and stopped at the first
output byte, BO-relative offset `0x2010`:

| Observation | Byte |
| --- | --- |
| Pass 1 actual, captured once by the failing comparison | `0xde` |
| Pass 1 expected, low byte of `0x7800c0de ^ 1` | `0xdf` |
| Pass 0 expected first output byte | `0xde` |
| Pass 1 complement-initialized first output byte | `0x20` |

Only this first mismatching byte was logged; the rest of the output was not
captured. The CPU comparison matched the current expected code, IB and guard
prefix through byte 8207 before failing at 8208. That confirms neither which
commands the GPU fetched nor visibility of the complete GPU result. In particular,
one byte matching the previous pattern does not prove the entire previous output
was replayed or that CPU cache invalidation is the missing operation.

| Pass (zero based) | Budget | Pending | Elapsed |
| --- | --- | --- | --- |
| 0 | 0 ns | yes | 6,482 ns |
| 0 | 50,000 ns | no | 29,897 ns |
| 1 | 0 ns | yes | 8,265 ns |
| 1 | 50,000 ns | no | 22,171 ns |

The two-second cap path was not reached. The same three read-only tunables were
zero after initialization and before the probe; no failing-submission or
post-failure sample was collected. Immediate FAIL/HOLD detection preserved the
connection and mappings. One serialized recovery completed; the startup observer
performed no GPU work. Independent result, retirement and final-state checks
verified the original image, 347 EFI files, 148 Microsoft files, 46 protected
files, two links and security/kernel collections unchanged. No new matching
diagnostic report was found. The consumed job was removed and GPU-off plus the
firmware framebuffer remain. The one-init/one-probe/one-recovery scope is closed;
no follow-up GPU trial is armed.

At the byte-diagnostic checkpoint, the offline investigation order was:

1. **Repeated-buffer and command freshness.** The probe rewrites the same BO and
   embeds each pass's pattern directly in its IB. Audit CPU-to-GPU IB visibility,
   GPU command/constant fetching and GPU-to-CPU output visibility together. A
   future diagnostic must isolate one of these directions with one controlled
   change and independent expected data; this run cannot choose a cache fix.
2. **Execution and retirement ordering.** Keep a correct-output requirement
   separate from sequence completion. Audit the compute IB and kernel completion
   fence path before treating retirement as proof that the new pattern ran.
3. **Elapsed-wait acceptance.** The original kernel and the timer candidate have
   both failed the same repeated-dispatch integrity gate. Keep the timing backport
   isolated until its own full gate passes; a byte observation on original34
   cannot accept it or establish a mouse/GUI/frame-rate improvement.

Source review of the default build34 confirms `doSubmit` and successful
`doWaitSeq` call `flushBos()`, while that helper returns immediately for mode 0.
The IB builder already emits `ACQUIRE_MEM`, and `gpuSubmit` appends `RELEASE_MEM`.
These facts explain why both visibility directions and ordering remain open;
they do not justify globally enabling costly BO flushing or changing packet bits
without a controlled test. No production code or tuning changed in this trial.

The default branch remains `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c` with
A1/A2/corrected-A3. Wait promotion remains blocked and accelerated-desktop HOLD
remains in force. Sanitized hashes, observations and explicit limits are in
[the byte diagnostic record](validation/upstream34-native-byte-diagnostic-20261116.json).
The earlier candidate, identical-binary control and host-only records remain
historical records; they have not been rewritten with the newly observed byte.

A separate [two-policy IB freshness diagnostic](NATIVE-IB-FRESHNESS-DIAGNOSTIC.md)
compares rewriting/reusing one IB slot with selecting
a pre-staged immutable slot while keeping the output BO/address and verification
unchanged between those policies. In a later, separate reuse-only build34 trial,
its new fixture reproduced pass 1 / `0x2010` / actual `0xde` / expected `0xdf`
after positive retirement. One recovery completed and the consumed startup job
was removed; fresh policy was not run in that scope. This is a reproduced
control signature. See the
[reuse control record](validation/upstream34-native-ib-reuse-control-20261116.json).

The separately continued fresh-only trial then used the exact same original34
image, source and binary. Its two immutable pre-staged IBs were selected in
sequence, and both complete 16-KiB comparisons passed, including the same
re-poisoned output address. It used three wait calls (25,037 ns, 35,226 ns and
42,479 ns); no two-second-cap wait was reached. Successful native cleanup was
followed by one planned recovery reboot to restore GPU-off. The observer made
zero GPU calls; independent result, retirement and final checks passed, with
the same protected manifests preserved and no new matching diagnostic report.
The consumed startup job was removed. See the
[fresh comparison record](validation/upstream34-native-ib-fresh-control-20261116.json).

The next investigation priority is the rewritten/reused-IB path: command
modification and IB-address reuse are coupled in this comparison and need
separate source-level review before choosing a fix. CPU-to-GPU visibility,
GPU caching/prefetch and execution/fence ordering remain possible explanations.
One trial per policy, in separate initialization/boot scopes, cannot establish
a specific root cause. The wait backport's full hardware gate remains a later
requirement; neither this result nor its short waits measures background-load
stability, GUI responsiveness or FPS. No production cache or packet change was
made. No further hardware scope is armed, and the earlier historical trials
above remain unchanged.

## Offline build40 validation boundary and rollback

Run the canonical committed-source harness and source checks from a clean tree:

```sh
python3 tools/test_context_retirement.py --out build/fence-wait-context-tests
python3 tools/test_bo_retirement.py --out build/fence-wait-bo-tests
python3 tools/test_queue_retirement.py --out build/fence-wait-queue-tests
python3 -m unittest discover -s tests -v
```

A native kernel build checks SDK/compiler/link compatibility only. No load,
GPU initialization, native desktop takeover, live unload, reboot or firmware
change is part of this canonical build40 validation. Keep the current
firmware-framebuffer containment and A1/A2/A3 HOLD status. Any future hardware
trial must isolate this one behavioral change on a matching baseline, preserve the rollback image,
and measure real fence progress and multi-client GUI latency under background
load before drawing a stability or frame-rate conclusion.

Source rollback is a normal revert of the correction commit. No runtime
rollback is required because this build is not installed. Never revert by
unloading an active GPU driver or by reusing the consumed earlier trial.
