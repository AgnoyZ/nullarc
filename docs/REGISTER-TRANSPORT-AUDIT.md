# Selector register transport audit

Status, 2026-11-15: **source/CPU validation only; no driver fix or target test**.
The latest [terminal VMID result](DESKTOP-VMID-PREFLIGHT.md#terminal-vmid-control-result)
remains a first-selection mismatch with both readbacks zero. This review finds
no demonstrated software address-unit or value-forwarding defect. Desktop
takeover and acceleration remain unproven; this boot stays terminal for GPU work.

## Addressing and earlier evidence

The fixed Linux reference is commit
`7d0a66e4bb9081d75c82ec4957c50034cb0ea449`. Its GC header defines
`regGRBM_GFX_CNTL` at offset `0x0900`, base index 1; VMID has shift 4 and mask
`0xf0`. The local CLI's `SEG1` calculation produces dword index `0xa900`, or
byte offset `0x2a400`, consistent with the generated header's block address.
These are static register offsets, not a publication of target BAR addresses.

Linux resolves SOC15 registers through the device's discovered base array. Its
GC 11.0.1 dispatch uses `gfx_v11_0`, which includes the GC 11.0.0 register headers;
the header filename alone is not evidence of a Phoenix mapping error. The
ordinary in-range register path scales dword indices by four, and the modern
device initialization maps PCI BAR5. The local provider also maps BAR5 and indexes
a volatile `uint32_t` pointer. This source comparison does not verify the live
mapping, cache attributes or hardware acceptance of a write.

Target base comparison is **already historical evidence**, rather than a missing
experiment: the [2026-11-13 discovery record](validation/ip-discovery-target-20261113.json)
reports validated GC 11.0.1 discovery data and matching GC bases, including both
direct `SEG` macros. That earlier result is not a fresh capture for the latest
VMID boot. Preserve it and the [earlier candidate instruction audit](
validation/gc-access-audit-20261113.json); neither establishes a selector cause.
This review additionally verifies that six relevant provider/client method bodies
still equal their counterparts in the historically accepted candidate source
`c5c22b420aa8990eff90df4cbddd29815793ecf6`. No live kernel memory was inspected.

Seven cached primary files match existing public reference-manifest hashes and
retain reviewed AMD MIT-style notices. Fresh downloads of `amdgpu_discovery.c`,
`soc15_common.h` and `gfx_v11_0.c` also match those bytes. No Linux function bodies,
whole headers or binaries were added to the repository.

## New CPU coverage

The existing desktop fake uses the CLI's `SEG1` macro for its own register bank.
It tests sequencing and failure handling, but a shared address error could pass.
The new `tests/test_register_transport.py` extracts the current local methods at
test time and compiles `tests/test_register_transport.cpp` with ASan/UBSan:

- CLI `checked_scalar`, `checked_method`, `rd`, `wr` and `grbm_select`;
- the actual client dispatcher, `shape`, `doReadRegs` and `doDbgWriteReg`;
- provider `rreg`, `wreg`, `writeReg` and `readRegs`.

The harness uses independent literal address/value oracles. It checks field
packing, dword units, adjacent-word preservation, full-width values, exact-end
and overflow rejection, read/write ABI refusals, the timestamp read exception,
handshake/closed gates and mutation refusal. Missing mappings and privilege
failures propagate to the CLI's terminal transport error, rather than becoming
successful zero replies. A synthetic lost-store injection produces zero through
both actual reply paths without claiming to reproduce the target's cause.

Only storage, IOKit marshaling, lock/reaper policy and unrelated dispatcher
branches are fake. The harness does not cover actual IOKit or PCI transport,
physical MMIO ordering/cacheability, kernel scheduling, lock/reaper implementation
or runtime binary identity. The existing complete CLI tests separately retain
the stop-after-mismatch behavior; this new harness does not run initialization.

All **43 focused methods** pass: seven new transport methods, 31 desktop methods
and five include-graph methods, with no skips. Four temporary mutated copies also
compile and fail the roundtrip oracle: shifted CLI address, divided dword index,
zeroed write reply and zeroed read reply. One initial read-reply mutation was
rejected at compile time for an unused pointer; the final version preserves the
volatile load before forcing zero and is independently detected at runtime.
Mutations affect temporary extracted files only. The full suite was not rerun.
The [validation record](validation/register-transport-audit-20261115.json) contains
the exact scope, hashes and results.

## Boundary and rollback

Production source, installed tools/drivers, startup, EFI and security settings
are unchanged. No service was opened on the target, no GPU command or reboot was
issued, and no consumed request was replayed. Raw traces and fake binaries remain
private. To roll back this test addition, revert it in a normal new commit;
preserve all historical target evidence and consumed scopes.

The remaining question is why the physical selector does not echo an otherwise
well-formed request under the observed conditions. This review supplies no basis
for changing register bases, cache attributes, timeouts, halt/reset sequencing or
readback guards. Continue with offline examination of existing evidence and the
initialization prerequisites. Any new physical experiment needs a separately
reviewed bounded request, a verified fresh boot and independent recovery.
