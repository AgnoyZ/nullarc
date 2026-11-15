# Check GART VMID selection before banked writes

Status, 2026-11-15: **source repair and CPU validation; uninstalled**. The
GART path previously ignored each selector write's immediate readback and
did not independently read the selector before writing `SH_MEM_CONFIG` and
`SH_MEM_BASES`. It also ignored the final idle-selection readback. A complete
transport reply alone therefore allowed a failed selection to continue into
banked writes and invalidation, and eventually report success.

This is a demonstrated software refusal gap, not an explanation of the
physical dual-zero result. The latest [desktop experiment](DESKTOP-RETEST.md)
stopped at the earlier KIQ idle guard, before reaching GART. Its consumed
request and recovery remain unchanged. The preceding [desktop guard repair](
DESKTOP-SELECTOR-GUARD.md) remains in the source candidate as well.

## Localized repair

`gart_select_vmid` in `tools/phxctl/mesboot.c` requires the immediate write
readback and one independent selector read to match the requested VMID value.
The GART loop calls it for VMIDs 0 through 15, and once more to restore the idle
selection. Each mismatch reports the phase, VMID, requested value and both
readbacks, then exits 75. Existing status/shape failures still exit 74.

The independent read is retained even after a complete but mismatching immediate
reply, so both observations remain available in the failure diagnostic. No
banked write for that transition, subsequent selection, restoration, CP_DEBUG
write, invalidation or checked-close completion follows the mismatch. A failed
idle restoration similarly stops before CP_DEBUG and invalidation. The desktop
caller cannot continue into MES, queue setup, seal or claim after this exit.

The successful path adds **17 register-read requests**. The 17 selector writes,
31 banked writes, other register values, write order, layout, memory writes and
invalidation policy are preserved. Earlier GART mutations have already occurred
at this boundary; failure does not roll them back or establish a reusable boot.
There is no new reset, timeout change, delay, retry, cleanup or power operation.
Only `mesboot.c` changes in production. No upstream body, header, binary or new
register definition was imported.

## Reproduction and verification

The actual CLI is compiled against fake IOKit with ASan/UBSan. The independent
write-count oracle checks every one of the 16 selections and the final idle
restoration, under the reference and relocated synthetic layouts:

- Immediate-only, subsequent-only and paired one-bit mismatches.
- Immediate and subsequent all-ones observations separately.
- Both readbacks zero for each nonzero VMID request. Zero is deliberately not
  injected as a failure for VMID 0 or idle restoration, where it is correct.

Before the production repair, **all 200 mismatch cases incorrectly exited
zero**. Afterward they all exit 75 with the exact diagnostic and terminal IO
counts. Two normal-layout cases retain all 188 register writes, 31 banked writes
and one invalidation acknowledgement; their register-read count is 50 instead
of 33. A separate desktop-entrypoint matrix has **98 cases**, checking every
transition's immediate/subsequent failure and every nonzero VMID's dual-zero
failure in both layouts. It verifies no MES snapshot, queue doorbell, seal,
claim or checked close follows the failed GART transition.

All **66 focused Python methods** pass without skips: seven selector methods,
seven GART runner methods, 33 desktop methods, seven register-transport methods,
five native-include methods and seven actual-observer methods. The existing
GART case generator and result oracle also pass **336 cases** against the
complete fake CLI, including failure at all 188 register writes and all 50
register reads. The full repository suite was not rerun.

Two temporary source mutations independently remove the immediate or subsequent
guard. Each compiles and incorrectly succeeds in 34 cases, which the respective
new regression detects. These mutations affect private copies only. One initial
test-selection script failed before compilation because it did not flatten a
nested unittest suite; the corrected run supplies the failure-first evidence.

The real x86_64 CLI and the observer that includes it compile and link with
IOKit/CoreFoundation. Their architectures were checked without executing either
binary. The CLI uses the existing repository build recipe; no new claim of a
strict warnings-as-errors CLI build is made. Exact input hashes and checks are
in [the validation record](validation/gart-selector-guard-20261115.json).

## Execution boundary and rollback

No live service, GPU command, signing/deployment, startup arming or reboot was
used for this repair. Installed components, EFI and security settings are
unchanged. Private logs, binaries, raw target evidence and all historical input
pins remain unpublished. No old request was repinned, replayed or rearmed.

The physical selector failure and desktop takeover remain unresolved. Continue
offline investigation of access and initialization prerequisites; a hardware
test requires a distinct reviewed scope binding the changed candidate, fresh
boot and independent recovery. Revert this source repair in a normal new commit
to roll it back; retain historical receipts and consumed authorizations.
