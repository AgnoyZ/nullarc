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
2. Insert compute-only single-word NOP padding **between the IB descriptors
   and RELEASE_MEM**, reserving the latter's eight dwords when aligning the
   final end. RELEASE_MEM stays the last packet. Its payload and all code from
   sequence allocation through write-pointer/history publication are unchanged.

The first published CPU-only prototype (`9e0f04c`) placed padding after
RELEASE_MEM. That ordering is withdrawn. Original34 advances `q.doneEnd` to
the submission's recorded `q.fend` when its completion fence retires. Padding
after that fence would leave a suffix beyond the completion packet while the
bookkeeping describes the entire padded frame as reclaimable. This is a
source-level ownership risk, not an observed hardware failure or proof of the
IB defect's cause. The revised ordering keeps the entire frame at or before
the fence. The withdrawn prototype never became a kernel candidate and was
never installed, loaded or executed on the GPU; its published history and
[original CPU evidence](validation/build34-ring-padding-offline-20261117.json)
remain available.

This is independently written test-only transformation logic. It neither
modifies `src/phxbringup` nor emits a kernel build, installer or hardware job.
Source drift, ambiguous extraction, repeated transformation or changes
outside those two sites are rejected. The protected original34 files are
checked before and after the run.

The fixture stubs locks, ring writes, VM binding, queue fences, HDP flushes and
MMIO with ordinary process storage. It checks all 64 admitted descriptor
counts, every alignment residue, representative ring/counter boundaries,
compute and graphics selection/fallback, canonical address emission,
descriptor and RELEASE_MEM words, fence placement at the very end, padding
counts, full-ring/history refusal,
one delayed retirement, bounded exhaustion, sequence/history bookkeeping,
both write-pointer halves and the CPU-backed doorbell. The arithmetic oracle
uses division rather than the transform's bit mask. It models **no CP, GPU
cache, DMA, real MMIO, concurrency or GPU completion**.

The source-defined compute adoption in `tools/phxctl/mesboot.c` uses a
**1024-dword ring starting at WPTR 8**. The native query's hardcoded 4096 is
not used as the actual adopted queue geometry here. For all 256 starting
alignment residues and 64 descriptor counts, the largest compute frame is
519 dwords; with the existing guard it needs 535, fitting an otherwise empty
1024-dword ring. Occupied-ring and history checks still apply. The fixture
also runs 70 successive submissions each for one and 64 descriptors, starting
from the initializer's geometry, with explicitly CPU-injected retirement.
These cases cross ring and 64-entry history-slot boundaries; they do not
model hardware completion.

On 2026-11-17 six recipe regression methods and **72,222 actual-function CPU
scenarios** passed: 36,111 each for original and revised padded source,
including 140 successive adopted-queue CPU submissions per policy. The padded
fixture added NOPs in 17,723 scenarios; 468 scenarios refused submission,
compared with 292 for the original fixture. The difference includes small
ring geometries for which a padded submission plus the original guard does
not fit. Those refusals are explicit compatibility work to review, not a
silent acceptance or evidence that all original configurations are preserved.
The earlier withdrawn prototype's first compile attempt found a missing
`ringOff` field in the CPU stub; its corrected fixture passed in a fresh
output directory. The revised ordering passed its first CPU run, then a
second fresh run after adding the successive adopted-queue cases. A separate
negative control compiled the exact withdrawn transformed function against
the revised fixture and stopped at the expected padding-placement assertion,
confirming the new check detects the old ordering. Its expected CPU assertion
is not a GPU test or sanitizer fault. See the
[revised sanitized evidence](validation/build34-ring-padding-before-fence-offline-20261117.json).

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
The [inactive source proposal](BUILD34-RING-PADDING-PROPOSAL.md) now pins the
two-site derived source and defines the fresh control/treatment order. It
leaves image identities and live admission unprepared; no kernel is built
and no test scope is armed by that document.
Subsequent owner continuation produced a separate
[private derived candidate](BUILD34-RING-PADDING-CANDIDATE.md), with native
compilation, signature and static identity verification only. The CPU audit
itself still emits no kernel; no image has been installed, loaded or tested
on the GPU by that preparation.
Do not relabel a downstream kernel as build34, reuse build41/build42, or
silently admit a changed image as the untouched original34 baseline.

The deployed original34 image, kernel source, ABI, production helper,
A1/A2/corrected-A3, runtime and admission policy remain unchanged. The native
single-IB defect is still unresolved; desktop, default waits and FPS remain
HOLD. No further hardware range is armed by this audit.
