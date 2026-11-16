# Fence wait elapsed-time correction

Status on 2026-11-16: **offline candidate; not installed or hardware validated**.
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

This correction is developed on `downstream/780m-tahoe`, starting at
`81bd11df4ffd775985a4ad40727f7a1f349b7365`. It does not replace the candidate's
baseline bring-up component or change the default branch
`upstream34/vram-layout-fix` at
`90bb06f6f9255cb5a16cc5eb87e78032566b2000`. The downstream kernel build marker
advances from 39 to 40 so future source/binary identification distinguishes it.
The installed build34 trial and current GPU-off startup state are not changed.

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
`validation/fence-wait-deadline-20261116.json`. All GPU/hardware flags
remain false. The passing rerun supersedes the earlier runner-contract failure.

## Validation boundary and rollback

Run the canonical committed-source harness and source checks from a clean tree:

```sh
python3 tools/test_context_retirement.py --out build/fence-wait-context-tests
python3 tools/test_bo_retirement.py --out build/fence-wait-bo-tests
python3 tools/test_queue_retirement.py --out build/fence-wait-queue-tests
python3 -m unittest discover -s tests -v
```

A native kernel build checks SDK/compiler/link compatibility only. No load,
GPU initialization, native desktop takeover, live unload, reboot or firmware
change is part of this validation. Keep the current firmware-framebuffer
containment and A1/A2/A3 HOLD status. Any future hardware trial must isolate this
one behavioral change on a matching baseline, preserve the rollback image,
and measure real fence progress and multi-client GUI latency under background
load before drawing a stability or frame-rate conclusion.

Source rollback is a normal revert of the correction commit. No runtime
rollback is required because this build is not installed. Never revert by
unloading an active GPU driver or by reusing the consumed earlier trial.
