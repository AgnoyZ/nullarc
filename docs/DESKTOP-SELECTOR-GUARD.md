# Require both desktop selector readbacks

Status, 2026-11-15: **source repair and CPU validation; uninstalled**. This
repairs a demonstrated refusal gap in `desktop_idle_queue`, not the cause of
the [physical dual-zero result](DESKTOP-RETEST.md#target-result-and-recovery).
There is still no successful desktop takeover or acceleration evidence.

## Confirmed defect and minimal repair

`grbm_select` returns the provider's immediate write readback. The desktop
queue-idle helper also reads the selector through the separate read path.
Before this repair, it logged both values on failure but checked only the
second. An incorrect immediate readback followed by a matching subsequent
readback therefore passed both the selection and idle-restoration checks.
That could allow the next banked queue read or next selection to proceed.
The VMID-only preflight and MES-start path already require both readbacks.

The repair changes exactly two conditions: selection requires both values
to equal the requested selection, and restoration requires both to be zero.
It adds no IO, register value, retry, timeout, cleanup, reset or initialization
step. The existing paired reads and failure diagnostics remain in place.
There is no checked service close after these fatal errors, just as before;
this change must not be described as verified target cleanup.

The observed physical request had **both** values zero for a nonzero request.
The old condition already rejected that case, and the repaired condition
still rejects it. This defect does not explain that physical failure and is
not evidence that the GPU now accepts selector writes.

## Reproduction and checks

The actual CLI fake now corrupts only the immediate reply at each of the eight
initial selection/restoration writes, leaving the synthetic register and its
subsequent read correct. A new matrix covers both `desktop-init` and
`desktop-preflight`, reference and relocated layouts, and all four queues and
their restorations: **32 cases**. All 32 failed the new refusal expectations
before the production repair because the CLI incorrectly returned success.
All 32 now return 75 and log the mismatching immediate and matching later
value. Exact IO counts verify that no later banked read, selection, VRAM write,
doorbell, seal, claim or checked close follows the failed check. The already
paired diagnostic read is retained.

All **51 focused Python methods** pass: 32 desktop-handoff methods, seven
register-transport methods, five native include-graph methods and seven
GC-observer methods. The actual CLI/provider/register/observer harnesses use
ASan/UBSan and explicit hardware/OS fakes. Two private mutations separately
remove each new condition; each compiles and causes the corresponding 16
matrix cases to return success incorrectly. The new oracle detects both.

The actual changed CLI compiles and links on x86_64 macOS using the repository's
existing native recipe. The actual GC observer, which includes the same CLI
source, also compiles and links with its existing warning suppression. Neither
native executable was run. An additional `-Wall -Wextra -Werror` attempt on
the standalone CLI fails on the existing unused `val` at line 700; the same
failure was independently reproduced from the unchanged parent source. The
normal native recipe passes for both versions. This is not a strict-warning
native pass, and the unrelated legacy declaration is left unchanged.

The full local suite was not rerun; no hosted result is claimed for this repair.
See the [validation record](validation/desktop-selector-guard-20261115.json)
for input hashes, before/after scope, mutation results and limits.

## Upstream order and execution boundary

The read-only upstream comparison uses pinned commit
`8aba872560a3c9b7dc7a0ddebfad001c6dddf315`, not an assertion about the latest
upstream. Its installer is byte-identical to the local installer and deploys
packaged helpers; it is not itself the selector initialization implementation.
Its `full.sh` runs firmware/power, doorbell/CP setup, GART and MES before its
requested queue step. The downstream desktop path performs its queue-idle
checks before doorbell/CP setup and GART/MES. This is an ordering difference,
not proof that moving activation writes before the checks fixes the selector.
The [separate historical GC observations](GC-STATE-OBSERVATION.md#fresh-boot-target-observations)
also do not establish such a dependency on the failed desktop boot. No upstream
installer/startup helper was executed, and this repair does not reorder them.

Installed helpers, drivers, collections, startup, EFI and security settings
were not modified. No service was opened on the target, no GPU operation,
arming or reboot was performed, and no closed request was replayed. Private
binaries and logs remain ignored and unpublished. Roll back the source repair
with a normal new revert commit; retain the historical target evidence.
Any later physical experiment needs a new reviewed scope and exact candidate
pins, a fresh boot and independent recovery. Existing consumed scopes keep
their original inputs and cannot be reused for this candidate.
