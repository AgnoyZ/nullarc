# Original34 outer-ring padding source audit

The [output-target comparison](BUILD34-IB-TARGET-SWITCH.md#separate-hardware-target-switch)
observed the previous pattern at old destination A while intended destination
B remained poison. It narrows the investigation but does not prove a CP/cache
root cause. This follow-up checks submission framing against pinned upstream
source, then exercises one minimal source idea with CPU fakes. **No kernel
candidate is built, installed, loaded or executed by this work.**

## Source findings

On 2026-11-17 the upstream `luuumi-dev/nullarc` default `main` was read at
`8aba872560a3c9b7dc7a0ddebfad001c6dddf315`. Its `PhxBringup.cpp` and
`gpuSubmit` are byte-identical to the approved original34 source. That
function emits four ring dwords per IB plus eight for RELEASE_MEM, advances
the software write pointer and publishes it without adding ring-end NOPs.
One descriptor therefore adds 12 dwords and two add 16. This is a specific
shared source gap, not an already available upstream default-branch fix or
an exhaustive claim about every PR.

For a stable comparison, Linux **v6.12**, commit
`adc218676eef25575469234709c2d87185ca223a`, was inspected rather than described
as the latest kernel:

- `gfx_v11_0_ring_funcs_compute` specifies `align_mask = 0xff` in dword units.
- `amdgpu_ring_commit` inserts NOPs to that boundary before publishing WPTR;
  its comment identifies fetch size as the reason.
- The compute hardware-IP query advertises 32-byte IB start/size alignment.
  The diagnostic's `0x1000` IB offset and 320-byte size satisfy those values.

The external IB size and the outer submission ring's fetch padding are
different checks. These findings justify investigating **outer ring
publication**, not declaring a requirement to enlarge the payload IB or a
proved cause of this machine's wrong value. The successful two-descriptor
NOP workaround remains compatible with multiple explanations.

Primary references, with immutable source pins:

- [nullarc gpuSubmit](https://github.com/luuumi-dev/nullarc/blob/8aba872560a3c9b7dc7a0ddebfad001c6dddf315/src/phxbringup/PhxBringup.cpp#L852)
- [Linux GFX11 compute ring functions](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L6846)
- [Linux ring commit](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ring.c#L140)
- [Linux hardware-IP alignment query](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_kms.c#L395)

The inspected Linux files carry MIT permission notices; no Linux function is
copied into this experiment. The actual nullarc function is extracted under
the repository's existing MIT option. Existing licences/notices and all
production files remain unchanged. Private reference downloads retain their
original notices. Source identities are recorded in the sanitized evidence.

## CPU-only source experiment

`tools/upstream34_layout/ring_padding.py` requires the exact approved source
and function hash, extracts the **actual** `gpuSubmit` into a C++ fixture, then
compiles and executes two CPU programs under ASan/UBSan. One uses the original
function unchanged. The other changes only two reversible sites:

1. Lock before calculating space; reserve the exact padded end based on the
   locked compute WPTR, while retaining the 16-dword ring guard. Unlock on a
   geometry refusal. Graphics keeps its original unpadded reservation.
2. Append compute-only single-word NOP padding before write-pointer/history
   publication. The IB descriptors and RELEASE_MEM payload remain unchanged.

This is independently written test-only transformation logic. It neither
modifies `src/phxbringup` nor emits a kernel build, installer or hardware job.
Source drift, ambiguous extraction, repeated transformation or changes
outside those two sites are rejected. The protected original34 files are
checked before and after the run.

The fixture stubs locks, ring writes, VM binding, queue fences, HDP flushes and
MMIO with ordinary process storage. It checks all 64 admitted descriptor
counts, every alignment residue, representative ring/counter boundaries,
compute and graphics selection/fallback, canonical address emission,
descriptor and RELEASE_MEM words, padding counts, full-ring/history refusal,
one delayed retirement, bounded exhaustion, sequence/history bookkeeping,
both write-pointer halves and the CPU-backed doorbell. The arithmetic oracle
uses division rather than the transform's bit mask. It models **no CP, GPU
cache, DMA, real MMIO, concurrency or GPU completion**.

On 2026-11-17 four recipe regression methods and **71,942 actual-function CPU
scenarios** passed: 35,971 each for original and padded source. The padded
fixture added NOPs in 17,583 scenarios; 468 scenarios refused submission,
compared with 292 for the original fixture. The difference includes small
ring geometries for which a padded submission plus the original guard does
not fit. Those refusals are explicit compatibility work to review, not a
silent acceptance or evidence that all original configurations are preserved.
The first compile attempt found a missing `ringOff` field in the CPU stub;
the corrected fixture passed in a fresh output directory. No native driver
was involved in that compile error or its correction. See the
[sanitized offline evidence](validation/build34-ring-padding-offline-20261117.json).

```sh
nice -n 15 /usr/sbin/taskpolicy -b python3 -B -m unittest discover \
  -s tests -p test_upstream34_ring_padding_recipe.py -v
nice -n 15 /usr/sbin/taskpolicy -b python3 -B \
  tools/upstream34_layout/ring_padding.py --out build/ring-padding-CPU-private
```

## Remaining gate

Passing CPU checks verifies the source transformation and stubbed submission
accounting; it does not establish that padding fixes the observed failure.
Before any modified-image hardware proposal, separately pin the untouched
baseline and any minimal candidate's source/image hashes, review ring-size
compatibility, preserve the original admission checks, and define strict
candidate-specific containment and recovery. No consumed original-image
scope, signed diagnostic receipt or CPU PASS may stand in for that work.
Do not relabel a downstream kernel as build34, reuse build41/build42, or
silently admit a changed image as the untouched original34 baseline.

The deployed original34 image, kernel source, ABI, production helper,
A1/A2/corrected-A3, runtime and admission policy remain unchanged. The native
single-IB defect is still unresolved; desktop, default waits and FPS remain
HOLD. No further hardware range is armed by this audit.
