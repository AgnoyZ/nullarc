# Allocation startup coordinator source candidate

Status, 2026-11-14: `tools/allocation_startup.py` implements a **source-only
coordinator and independent recovery dispatcher**. It has no installer, CLI,
default target commands or native acceptance adapter. Its integration tests
execute the actual coordinator, observer and dispatcher in separate processes,
using synthetic identities and file-only commands. This is an implementation
step toward Phase B, not an installed startup path or a desktop reproduction.

Build 37 is installed and loaded on macOS 26.7.2 build 25G332 and
[Phase A passed](ALLOCATION-PHASE-A.md). That boot's inherited initializer
already ran before those passive reads. They cannot be reused as this
candidate's pre-initializer baseline. The owner's outstanding request for
one desktop attempt remains unconsumed; remaining native integration work,
rather than a request to repeat general permission, prevents execution.

## Admission and stage ordering

The caller must run in a dedicated, single-threaded interpreter and provide
the reviewed identity/framebuffer readers, actual observer job, complete
initializer, claim, display, release and monitor commands. Exact executable
and declared input hashes are checked under trusted, nonsymlink parent paths.
Declared inputs are not automatic discovery of an executable's dependencies;
the interpreter, imports, dynamic libraries, firmware, configuration, source
provenance and semantic effects still require their own delivery review.
This module does not make an arbitrary command safe to run as root.

1. A durable `startup.started` claims the supplied fixed approval scope. It
   stays consumed on every outcome. The scope must be bound to the approved
   attempt externally; selecting a different directory is not authorization
   to replay it. Concurrent processes using that scope cannot both proceed.
2. Recovery is armed before the observer starts. The observer alone owns
   its new baseline and at most one failure read. The coordinator does not
   issue another snapshot request or poll the snapshot selector.
3. The observer's optional readiness callback runs only after the completed
   baseline and the first post-baseline report scan finds no new candidate.
   Reports discovered during baseline, an expired window or an observer
   failure produce no readiness. The existing CLI has no new options and
   its default behavior remains unchanged. `observer.started` is still not
   sufficient admission evidence.
4. Admission strictly checks the message fields/types, full baseline schema,
   spec, boot/OS/service/build/loaded-image identity, SHA-256 and remaining
   first-four capacity. Boolean values cannot stand in for integers. A known
   dead observer, an already pending recovery, early trigger, changed file,
   missing baseline or expired deadline prevents initialization.
5. Commands run in the fixed order `initialize`, `claim`, `display`, `release`,
   `monitor`. Each must explicitly return zero before the next stage. The
   coordinator checks identity, baseline integrity and the selected framebuffer
   before and after stages; between those checks it observes only owned
   process/pipe state, local trigger markers and deadlines. It does not poll
   native identity or framebuffer adapters during a waiting stage.
6. Before release, the selected framebuffer must remain held with no panel
   client open at each check. After the release command it must be unheld,
   and after the monitor it must also have an open panel client. A failed
   prerequisite skips later stages and requests independent recovery. Only
   successful monitor completion permits dismissal of that recovery owner.
   Once release has been admitted, first-report collection or observer exit
   does not itself request fallback: the reviewed monitor must retain the
   original crash thresholds. Before release admission those same conditions
   still refuse any new workload. The concrete packet must allow its unchanged
   90-second monitor within the absolute watchdog deadline; the library's
   generic per-stage default is not production monitor acceptance.

The monotonic hash-linked startup journal records recovery arming, admission,
the receipt's completed-baseline time/hash, stage requests/returns and monitor
completion, together with the private boot/service/image identity. Journal
records are individually flushed and fsynced. Stage stdout and stderr are
separate private files, each capped at 128 KiB through nonblocking pipes;
excess output refuses further stages. Commands run without a shell wrapper
or `preexec_fn`; a caller may still explicitly supply a reviewed interpreter.

## Independent recovery behavior

The recovery process owns the original absolute watchdog deadline and its
own session. The default is the reference full wrapper's 240 seconds; fake
tests shorten it. This does not extend or rearm the framebuffer's independent
120-second hold. The source preserves the existing asynchronous AGDC handler,
driver behavior, VM guards, budgets, pin direction and cleanup policy.

A failure request sets a shared one-byte pending state and writes a bounded
control pipe. Coordinator death closes that pipe, including after the observer
has inherited and closed its copy. Recovery also acts at its original deadline
without either event. Known pending state prevents later stage admission
before a recovery result file has been published. Control-pipe EOF is removed
from the wait set instead of repeatedly selecting a permanently readable FD.

Recovery dispatches the reviewed `disarm` and `display` helpers separately.
Display completion never gates disarming or reboot. A zero disarm status
permits the early reboot request; if disarm refuses or blocks, the original
watchdog deadline still permits that request. Recovery stdout/stderr are
discarded, so a noisy or nonreturning helper cannot fill a log or require a
drain before dispatch. Private evidence is published after the reboot request,
with helper PIDs/statuses and explicit unverified-fallback flags. Neither the
observer, a stage, a kill nor a reap is a recovery prerequisite.
The receipt includes its owner's PID, the frozen expected identity and the
durable attempt-claim hash, linking it to the startup journal's arming record.
An expected identity in a refused attempt is not a verified live identity.

Cleanup signals only owned stage groups and the observer. It makes no blocking
reap request and never kills the independent recovery owner. A persistent
caller must invoke `reap_owned()` later to collect its exact completed workers;
the retained registry does not signal unrelated processes. Recovery helpers
still running when their owner exits are reparented. The tests clean their
exact fixture workers, including intentionally blocked helpers. This library
does not supply launchd lifecycle or service-unload survival guarantees.
Darwin signal errors for an already-exited, unreaped process group are retained
without skipping observer cleanup or replacing the original refusal. A signal
request is not proof of termination or IOKit cancellation.

## Executed tests and remaining target gates

`tests/test_allocation_coordinator.py` exercises the actual implementation,
rather than a stub claiming that some other recovery process can run:

| Injected condition | Required observed behavior |
| --- | --- |
| Valid baseline and ordered file-only stages | Full stage order, linked monotonic trail, dismiss only after monitor, no desktop-validity claim |
| Actual collector with fake metadata commands and fake reader | Nine successful baseline command statuses, admission through actual observer, no extra failure read |
| Blocked/dead observer or coordinator death | No new admitted stage; real dispatcher requests fixture recovery independently |
| Missing/malformed/late/changed baseline, early report or exhausted capacity | Initialization refused, fixed scope retained |
| Report or blocked failure collector after readiness | No later claim/release; dispatch never waits for collection |
| First report after display release | Collection completes while the actual coordinator leaves the monitor's crash-threshold decision intact |
| Boot/service/image/build change, expired hold or changed baseline after initialization | Later stages refused |
| Failed/blocked initialization or claim; excessive command output | No later display/release; owned command cleanup only |
| Failed monitor or failed release boundary | Recovery remains active |
| Display-recovery helper blocked | Disarm and reboot request still proceed |
| Disarm refuses or blocks | Reboot request occurs at the original absolute watchdog deadline |
| Recovery already pending before its result file exists | No initialization |
| Competing process using the same fixed scope | Exactly one accepted attempt |

These observations cannot establish progress under an uninterruptible kernel,
bus, filesystem, fork/exec or whole-system hang. They do not prove that a
requesting helper actually changed NVRAM, disabled startup, restarted the OS,
or returned to a usable firmware desktop. A dead recovery owner prevents new
stage admission when detected; it does not itself provide another recovery
owner. The independently usable operator recovery route remains necessary.

Readiness means that no new report was found in that particular first scan.
It cannot establish crash causation or exclude an arrival immediately after
the scan. Shared pending/liveness checks refuse known failures; they cannot
atomically cancel an already admitted or in-flight IOKit operation. A late
held/unheld read also cannot prove the historical 120-second timer/panel-open
ordering. A concrete adapter must retain that history and refuse ambiguous
ordering rather than treating these point observations as sufficient proof.

The still-missing native chain must preserve the explicit GART/MES layout
contracts and checked transport, prove both engine handoffs and required
resource ownership, and provide the real display/monitor/disarm commands.
The installed legacy mesboot binary still lacks exact build/source provenance
and has known unchecked transport paths. The [initializer contract review](
ALLOCATION-INITIALIZER-CONTRACT.md) and [resource handoff review](
ALLOCATION-QUEUE-HANDOFF.md) remain applicable. Neither a generic callback
nor this fake-process suite satisfies those native gates. Build 38 remains
uninstalled. No new M2 attempt, GPU initialization, live snapshot request,
startup change, driver installation or reboot was performed for this source
candidate. Raw logs and fixture process evidence remain ignored and private.

## Local verification, 2026-11-14

A clean isolated committed snapshot passed **570 full-suite tests** under
Python 3.13.18 in 337.853 seconds, without skipped tests. The
actual source, test and workflow hashes remained unchanged and matched the
candidate checkout before and after every suite. Apple Python 3.9.6 separately
passed **90 focused tests**: 64 collector/coordinator tests in 74.496
seconds and 26 observer tests in 5.173 seconds, with no ResourceWarnings.
The coordinator contributes 43 test methods, including real multiprocess
integration cases; the observer adds three readiness-callback methods.
Full-suite SQLite ResourceWarnings arose
during unchanged GoalResume fixtures and were retained in the private log.

The first full-suite invocation used the dirty checkout and was stopped
after the expected clean-source staging refusals. It is not counted as a
passing full-suite run. The final clean snapshot includes the post-release
monitor-boundary and recovery receipt identity/hash corrections. The
[validation record](validation/allocation-startup-coordinator-20261114.json)
contains tested input hashes, exact test counts and the remaining native
gates. This verification made no live snapshot request or target change.
