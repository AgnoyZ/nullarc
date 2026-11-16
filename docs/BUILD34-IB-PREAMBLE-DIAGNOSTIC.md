# Original build34 IB preamble diagnostic

Status on 2026-11-17: offline investigation, not a proven IB fix. The second
reused-IB dispatch still has an unresolved first mismatch at BO byte `0x2010`:
actual `0xde`, expected `0xdf`. The latest original34 prerequisite result is
recorded in [the PR28 gate evidence](validation/build34-pr28-install-gate-20261117.json).
Desktop acceleration and default wait promotion remain on HOLD. No FPS claim
follows from these tools.

## Hypothesis and one-variable comparison

Earlier independent original34 trials distinguished rewriting/reusing one IB
address (failed) from submitting two already-written distinct IB addresses
(passed for two guarded dispatches). CPU CLFLUSH/MFENCE on the rewritten IB and
the separate MEC doorbell-range treatment both failed to remove the same wrong
value. These observations motivate a command-fetch/publication investigation;
they do not establish its root cause. Only the first mismatching byte was
reported, so the entire output must not be described as the old pattern.

`tools/upstream34_layout/ib_preamble_probe.cpp` uses the existing multiple-IB
native ABI with the exact original34 kernel. Both policies submit the same two
IB descriptors, in this order, twice:

1. A prewritten immutable eight-dword preamble at BO offset `0x1400`.
2. The 80-dword dispatch IB at `0x1000`, rewritten only before pass 1.

The control preamble is one eight-dword Packet3 NOP. The treatment preamble
is an eight-dword GFX11 ACQUIRE_MEM. The preamble bytes are the only policy
difference. Neither policy uses the prewritten pass-1 slot at `0x1200`; that
slot stays guarded. Both retain the same 79-dword reference shader, 16 KiB
GTT allocation, `0x2010` 1 KiB output, poison, canary, pass patterns and 250 ms
inter-pass pause as the frozen original34 CPU-publication control. All 16 KiB,
including both slots and the preamble, are checked after each retirement.

This is a new fixture: the original one-IB failure does not replace a fresh
NOP-preamble control. CP prefetch could also fetch the second IB before the
first completes; placing ACQUIRE_MEM in another IB is not proof that its
invalidation precedes all relevant command fetches. A negative result would
reject this placement for this trigger, not every possible synchronization
fix. The existing ACQUIRE_MEM inside the dispatch IB is preserved.

## Source review and licensing

The encoding was independently checked against Linux commit
`adc218676eef25575469234709c2d87185ca223a`, specifically
`drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c:gfx_v11_0_emit_mem_sync`,
`nvd.h` and `soc15d.h`. The exact `gfx_v11_0.c` blob is
`d3e8be82a1727a7839040bb82291a742de4409e8`, SHA256
`74dc38ba2d48b1e43db0bec0706a53385fb2f083b273a8f8f4ee2da5d3e06317`.
The preamble has a 24-bit high coherency-size field and GCR control `0xc3b1`:
GLI invalidation (bit 0), GLM writeback/invalidation (4/5), GLK/GLV/GL1
invalidation (7/8/9), and GL2 invalidation/writeback (14/15). NOP opcode
`0x10`, count 6 means eight total dwords. This is encoding review, not evidence
that Linux resolves this machine's fault. No Linux implementation is linked.

`ib_preamble_packets.h` is a narrow extraction of the existing reviewed
diagnostic packet builder and the libdrm 2.4.123
`tests/amdgpu/shader_code_gfx11.h` reference shader. Its AMD 2022 MIT notice is
retained. The shader's 316-byte little-endian image SHA256 is
`735ea6ea8faa4e398ee231d55e9f80ec5c577346c333533ab2417f9beb2b795c`.
Only the dispatch builder is retained; unrelated MES/GART helpers and direct
fence-emission code are excluded. The mock ABI fixtures derive from the
existing native-diagnostic tests. No PolyForm plugin, firmware or binary is
copied into this source addition. Existing licences and notices are unchanged.

## Offline checks

```sh
make test-upstream34-ib-preamble
python3 tools/upstream34_layout/ib_preamble.py build/ib-preamble-native-private --compile
make test-upstream34-layout
```

Use fresh output directories. The preparation recipe compares protected
kernel/helper/licence inputs with approved checkpoint
`64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`, freezes the probe, shader and
unchanged native ABI/topology headers, and records hashes. Native compilation
only compiles, signs and checks the signature and x86_64 architecture. It never
executes the resulting binary, including with invalid arguments.

The actual probe is separately compiled with fake IOKit/CF under ASan/UBSan.
The fixture independently checks request size, two-IB order, packet bytes,
full arena staging, zero/short/capped waits, strict CLI/PCI/ABI/build admission,
and terminal HOLD paths. It corrupts each shader, dispatch, unused-slot,
preamble and output region, and injects stale pass-0 bytes into pass 1 for
**both** policies. The mock does not make memsync cure the stale result.
These are CPU safety/continuation checks, with no GPU ISA/cache/coherency
simulation. They cannot authorize acceleration or establish an IB fix.

On 2026-11-17, all 4,560 actual-C++ ASan/UBSan cases (1,140 for each
policy/VA combination), six result-parser regression methods and 20 original
layout regression methods passed with no skips. Nine private controller mocks
also passed. The native x86_64 probe compiled with warnings treated as errors,
was ad-hoc signed, and passed strict signature/architecture checks without
execution. Protected production sources and licences remain unchanged. See
[the offline validation record](validation/build34-ib-preamble-offline-20261117.json).

## Hardware scope and recovery

The source addition neither installs/loads a driver nor creates a startup job,
initializes the GPU or arms execution. Build41/build42 remain withdrawn and
are rejected as synthetic identities before any context/BO allocation.

A subsequent original34 hardware comparison requires a fresh separate bounded
scope for each policy. First reproduce the wrong value with the new NOP
control and complete its recovery. Only then consider a separate treatment
from a fresh GPU-off boot. Verify the exact original kernel image, ABI 1.12,
PCI `1002:1900`, native readiness, source/binary hashes, unchanged protected
files, EFI and security state, and an independent live recovery witness before
GPU work. Limit each scope to one original initialization, one client, two
dispatches, and at most one recovery reboot. Do not reuse any consumed packet.

The probe initializes nothing and claims no display. Any uncertain execution,
timeout, malformed response, non-positive retirement or byte mismatch prevents
another dispatch and retains the connection/mappings in HOLD. An external
independent controller must return to GPU-off with the firmware framebuffer;
do not kill a held process or attempt live cleanup. Even a treatment PASS is
only this bounded diagnostic result and does not clear the desktop HOLD or
admit a production RADV fix. No automatic retries, global environment changes,
driver deployment, EFI/NVRAM writes or security changes are part of this step.
