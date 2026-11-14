# Allocation capture runtime delivery

Later on 2026-11-14, the owner-authorized
[build-37 deployment](ALLOCATION-BUILD37-DEPLOYMENT.md) installed the retained
candidate and independently verified it on EFI. The subsequent
[postboot Phase A validation](ALLOCATION-PHASE-A.md) verified its actual load
and exactly two successful same-boot passive reads. The no-install and
not-yet-loaded statements below describe this earlier runtime-preparation
pass. The observer/startup integration and desktop reproduction remain open.

On 2026-11-14, after the request for a single desktop reproduction with
collection, a fresh read-only target check still found **PhxBringup build
36** on macOS **26.7.2, build 25G332**. Its loaded-image identity matched the
retained build-36 deployment. IONDRVFramebuffer was present, the two available
display gates read zero, and the selected display-arming value and named
startup markers were absent. Two other queried gates were unavailable, not
assumed zero. The bounded named-helper query found no competitor. Boot
identity matched before and after the check.

Build 36 does not contain the build-37 allocation snapshot interface. A new
desktop attempt on the currently loaded kernel cannot use the retained
snapshot reader to obtain that missing history. The earlier failed attempts
already showed that subsequent unified-log collection alone did not recover
the required kernel allocation records. This is why the existing reader and
observer source are not yet an installed collection path.

## Trusted runtime gap closed

The prior [continuity/input review](ALLOCATION-RESUME-REVALIDATION.md) identified
a missing trusted Python/helper delivery. This pass tested the two collection
suites using Apple's installed Python **3.9.6**: all **21 capture tests** and
all **23 observer tests** passed, with no skips. These are focused results for
these helpers, not a claim that Python 3.9 supports the repository's complete
test suite. The observer suite includes its temporary-directory native kqueue
test; no test opened a target driver service.

The exact `allocation_capture.py` and `allocation_observer.py` bytes from
commit `e75e33f9b217ceace2c2d60eeddf013641297554` were then staged in a new
root-owned private directory. Two small entrypoints invoke them with the
system interpreter under `-I -S`, explicitly adding only the trusted helper
directory. This avoids user site packages, environment Python paths and
global site initialization. Both entrypoints passed their `--help` check.
Neither invoked the reader.

An independent process verified all four staged files, the interpreter, and
**86 imported-module file records**, checking their retained hashes and root-owned,
non-group/world-writable resolved paths. The retained reader hash and strict
signature were verified during staging. This is a retained private runtime
delivery, not an installed LaunchDaemon or startup integration. Raw paths and
the module/file manifests remain private.

The same independent read-back also rehashed all **337 retained EFI-backup
files / 105,882,009 bytes** against their original manifest. EFI was not
mounted or compared with the current volume in this pass. This verifies
backup bytes; independent recovery remains operator-attested, not boot-tested
by the agent.

## Next target boundary

The [build-37-only install/rollback packet](ALLOCATION-INSTALL-PACKET.md)
remains the concrete next package. Its instrumentation preserves the old
claim behavior, which isolates the diagnostic experiment from the separate
build-38 admission correction. Neither candidate was installed by this pass.

Before a desktop reproduction, first load the exact reviewed build-37
PhxBringup through a separately scoped normal firmware-desktop restart and
verify the two same-boot passive reads required by
[Phase A](ALLOCATION-EXECUTION-PLAN.md#phase-a-prove-passive-read-feasibility-on-the-firmware-desktop).
An exact new install/restart operation must respect the owner's prohibition
on automatic driver deployment. The request for one desktop reproduction
does not consume any old grant or establish that these prerequisite
operations have already happened.

After successful passive validation, complete the concrete pre-workload
observer/startup and independent-recovery integration review in Phase B.
Staging an interpreter and two helpers alone does not establish the baseline
ordering, compatible initializer, loaded candidate, or failure collection.
Do not execute an old one-shot helper or start the inherited legacy scripts
manually to substitute for that integration.

This pass performed **zero target snapshot requests, driver installations,
startup edits, GPU operations, M2 arming or restarts**. No new failed-boot
history was obtained, no automatic restart continuation was assumed, and the
allocation/desktop root cause remains unresolved. The
[validation record](validation/allocation-capture-runtime-20261114.json)
keeps the completed runtime preparation separate from those target steps.
