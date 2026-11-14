# Build-37 passive snapshot validation

On **2026-11-14**, the authorized normal restart completed. The new boot
started at **11:16:31 +0800** on macOS **26.7.2, build 25G332**.
Postboot verification completed at **11:21:59 +0800** and matched the exact
installed build-37 image from source
`2c26f4deffc4940c1a0a69d9b36c6770191ee0a8`. Its executable SHA-256 is
`6e59fe0d3a1247b70eae7b1953268a1239c5b5524870fbb9cdfc3e80783203a1`.
This extends the earlier [installation record](ALLOCATION-BUILD37-DEPLOYMENT.md)
with actual load and passive-read evidence.

## Loaded state and preserved installation

The verifier checked the new boot and exact loaded-image identity, one
PhxBringup service, one NMXAccel service, one IONDRVFramebuffer and no
PhxAMDFB. Both available display gates were zero; display arming and the
named startup markers were absent. The inherited firmware-desktop startup
had completed. A read-only EFI comparison matched the entire 340-file
post-installation manifest, including the retained build-36 rollback bundle;
EFI was unmounted afterward. Runtime, plugin, selected startup inputs and
PhxAccel remained unchanged.

## Exactly two passive reads

The trusted [capture runtime](ALLOCATION-CAPTURE-RUNTIME.md) performed one
baseline at **11:23:05 +0800**, followed by one matching second read at
**11:23:43 +0800**. There was no added GPU workload between them. The helper
calls its second phase `failure`; that name does not mean a failure was
induced. Neither the report observer nor desktop takeover ran.

All **18 retained command statuses** were successful and not timed out.
The four before/after identity brackets matched the same boot, OS build,
service and loaded image. Both full snapshot schemas validated. The second
result linked the exact baseline hash and matched the independently
recomputed comparison. Each durable attempt marker remains consumed; no
reader was retried or invoked from a replacement output directory.

Both snapshots reported **zero observed refusals**. All seven reason counters
and their deltas were zero, and no reason's four-record capacity was
exhausted. This proves that the bounded software-history interface and its
same-boot comparison were readable in this state. It does not exercise any
refusal writer, reproduce an allocation failure or demonstrate recovery
while a GPU or kernel call is blocked.

Postflight metadata at **11:24:17 +0800** preserved the firmware framebuffer,
display gates, absent arming and startup markers, installed runtime/plugin
and selected startup inputs. An independent review at **11:31:18 +0800**
reread the original private evidence, revalidated the schemas, all 18 saved
statuses, identity brackets and comparison, and checked matching current
metadata. That review made **zero additional snapshot requests**.

## Continuation and the next execution boundary

The existing login continuation resumed its saved session after this actual
normal restart. Its process, saved-session log and per-boot claim supplied
evidence of this particular restart/resume; they do not guarantee all future
boots or recovery from a hard hang. At the owner's request, the duplicate
continuation was then stopped and its exact login service disabled. A
separate read-back verified its processes absent and the current session
preserved. Conversation data and Goal status were not deleted or changed;
driver startup and recovery services were not changed.

The inherited initializer and claim had already completed before this
baseline. **Phase A therefore passes; a pre-initializer baseline and a
diagnostic desktop reproduction remain unperformed.** Phase A output must
not be reused as a future observer's baseline. The concrete initializer,
observer admission ordering and independent recovery integration still
require the [Phase B review](ALLOCATION-EXECUTION-PLAN.md#phase-b-review-startup-admission-and-recovery-before-a-display-attempt).
The separate build-38 claim correction remains uninstalled.

No additional installation, initialization, M2 arming, reboot or desktop
attempt occurred in this validation. The old failure's pending-versus-invalid
retirement distinction and host-import preparation stage remain unknown.
The [sanitized validation record](validation/allocation-phaseA-20261114.json)
contains aggregate evidence only; raw identities, reports, paths and
command output remain private.

## Offline regression checks

A fresh Apple Python 3.9.6 run initially passed 19 of 21 capture tests; two
content-only fixtures exceeded the unchanged shared five-second budget
while repeatedly starting Python. Those fixtures now use real `/bin/cat`
processes and a shell fake reader to return the same synthetic bytes.
The separate Python-based failure, timeout, output-limit and owned-process
termination tests remain intact. No production capture code, target timeout
or retained runtime byte changed.

After this fixture correction, all **21 capture tests** and **23 observer
tests** passed on the same system interpreter, with no skips. These are
focused offline regressions, including the native temporary-directory
kqueue test; they perform no live driver requests. JSON, local documentation
links, publication privacy and `git diff --check` were checked separately.
