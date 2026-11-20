# Build34 R3 device-fence observation contract

November 21, 2026: the exact observer's device reader is still **unbound**.
The original build34 driver, legacy `queueFence()` and installed runtime have
not changed. This document records primary-source review and one tested
arithmetic primitive; neither admits a hardware reader or kernel candidate.

## What the reviewed sources establish

Source identities, file digests and licence reviews are recorded in
[the source manifest](validation/build34-r3-fence-reader-sources-20261121.json).
The snapshots are upstream source references, not a claim that their versions
match the installed kernel, SDK or GPU firmware. Source downloads remain
private; no upstream implementation or binary was copied into this repository.

- Linux v6.12, commit `adc218676eef25575469234709c2d87185ca223a`,
  `amdgpu_fence.c:115–126`: `amdgpu_fence_read` obtains a little-endian
  **32-bit** fence. Its normal per-ring emission increments a 32-bit ring
  sequence; it does not reconstruct this project's shared global sequence.
  The same file initializes bounded fence slots and a fallback timer.
- At that same commit, `gfx_v11_0.c:5685–5717` selects RELEASE_MEM's
  32/64-bit data width and interrupt mode independently. It writes the GCR
  cache controls and enforces address alignment for the selected width.
  The function is not a guarantee of atomic GPU-to-CPU 64-bit loads through
  this project's BAR0 mapping. `amdgpu_ring.c` routes normal ring fence
  addresses through its writeback allocation, not this project's adopted
  BAR0 offset protocol. These are material differences to preserve in review.
- XNU `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`,
  `IOMemoryDescriptor.h:985–990` and `IOMemoryDescriptor.cpp:5668–5672`:
  `getMapOptions()` exposes mapping options, including caching settings.
  The mapping implementation also resolves default caching in context.
  These source interfaces are not a readback of the current device mapping
  or a proof that cached data cannot be returned.
- IOPCIFamily `4822b27a36e2de70e231ecf2bf3021384fab6ec2`,
  `IOPCIDevice.cpp:1429–1442`: `mapDeviceMemoryWithRegister` obtains the
  matching range and delegates mapping with its options. The call alone
  does not establish this project's actual effective cache attributes.

The reviewed Linux files carry MIT-style grants; the XNU files carry APSL 2.0
headers and the IOPCIFamily file an APSL 1.1 header. This was a read-only design
review, not a conclusion that all upstream components have the same licence.
The existing repository licence files and notices remain unchanged.

## Build34 facts and limits

The frozen production file `src/phxbringup/PhxBringup.cpp` has SHA256
`81f45aa2e8166bc6ebed4106129bebebfd70f9b4bbea6dbe389be46263e3c699`.
It maps BAR0 without an explicit cache option at the callsite. Its comment
calls BAR0 write-combined, but a comment cannot replace mapping admission.
Adoption seeds the queue's fence with two CPU dword stores. Submission emits
RELEASE_MEM with `DATA_SEL=2` and no interrupt, using the global sequence.
The legacy reader combines two volatile dword loads into a 64-bit value.
The packet's width does not by itself prove those two reads are one atomic
observation. CPU-to-GPU `sfence`/readback/HDP publication does not automatically
prove the reverse direction's atomicity or cache coherency.

A high/low/high retry also needs a device write-order argument. It must not
be accepted simply because the high words happen to match. For example,
across `0x00000000ffffffff -> 0x0000000100000000`, an intermediate high-new,
low-old value can be larger than work that has actually completed. Bounding
it by a later submitted value does not necessarily detect that case.

## Tested reconstruction primitive

The original [FenceWindow32](../tools/build34_exact_fence32.h) does **not**
load device memory. It reconstructs a value from a genuine aligned coherent
low dword supplied by a serialized caller. Its state consists of a generation,
a proved completion floor and a submitted upper bound. It allows a new
submission only when the sequence increases and the entire interval width is
strictly less than `2^32`. The interval therefore contains at most one value
with the observed low dword. Future or regressing samples outside that
interval refuse without altering output or state. Invalidation closes the
window; only a strictly newer generation can reseed it, while it is closed.

The bound counts **global sequence distance**, not outstanding jobs. One
submission after `2^32` jobs on the other queue is already ambiguous.
A future integration must validate before irreversible packet writes and
must account for every submission on a shared queue, including legacy clients.
It must never mask off a wide gap and declare old data complete. Refusal may
require a separately proved drain/reseed or backpressure; this primitive does
not implement either. It is not a solution to arbitrary unbounded global gaps.

ASan/UBSan passes **189,198 checks**, exhaustively enumerating 2-, 3- and
4-bit model intervals, plus 20,000 sustained 32-bit steps across multiple
wraps, exact `2^32` boundaries, holes, independent queues, identity changes
and 64-bit exhaustion. Twelve deliberately defective variants are detected.
It compiles as C++14 with exceptions and RTTI disabled. This externally
serialized arithmetic test requires no thread or device runtime; TSan and
native Kernel SDK compilation were not performed for this primitive.

The fixture also preserves a **counterexample to unconditional safety**:
an arbitrarily stale low dword from a whole earlier wrap can alias a value
inside an otherwise valid interval. The decoder cannot distinguish that
from a genuine new completion. The successful arithmetic checks therefore
depend on a coherent, non-regressing same-generation device load; they do
not prove that assumption. See [test evidence](validation/build34-r3-fence32-offline-20261121.json).

## Required native integration

1. Establish an aligned dword load with admitted effective mapping/cache
   attributes, correct endian/ordering semantics and the actual RELEASE_MEM
   visibility contract for gfx1103. Refuse unknown mapping modes; do not
   change the working BAR mapping or add a cache alias without an audit.
2. Seed the actual device fence before publishing queue readiness. Bind the
   arithmetic generation to adoption/fault/sleep/stop invalidation, with a
   trustworthy queue ownership/drain policy. Identity labels alone cannot
   prove an old queue stopped writing the same physical location.
3. Enforce the window before all irreversible submissions sharing that
   fence. Use bounded observation/backpressure outside global locks where
   appropriate; preserve R1b and the safe global retirement contract.
4. Integrate the read into exact observation with terminal-gate checks around
   the device access. Never treat a failed or unavailable read as completion.
5. Review legacy global retirement and queue-history consumers as well.
   Keeping an old path unchanged is not a new atomicity or resource-drain
   proof. In particular, receipt completion is not permission to recycle a
   VMID or release a BO still reachable by any GPU work.
6. Use actual pinned-SDK integration and finite, separately admitted GPU
   evidence before trusting the reader. No CPU test can accept hardware
   coherency, a physical frame rate or long-term stability.

No reader has been assigned by this work. The earlier exact observer still
fails closed without its CPU-fixture reader. No installation, kernel build,
live mapping query, GPU execution or power action took place. Continue the
[R3 ledger](BUILD34-R3-PLAN.md); this review does not complete R3.
