# Selective CPU IB publication diagnostic

Status on 2026-11-16: **offline diagnostic; not hardware-tested**. The earlier
[paired trial](NATIVE-IB-FRESHNESS-DIAGNOSTIC.md#original-build34-fresh-comparison)
failed its reused/rewritten IB policy and passed its immutable fresh-slot policy.
That comparison motivates a narrower test; it does not establish a production
cache defect. Both earlier scopes are consumed and may not be replayed.

## Submission-path review

Review covered default build34 at `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`
and downstream build40 at `792fbb78bde31a3c9bf03924a132b5cae6cf56b8`.
Both native submission paths emit `INDIRECT_BUFFER` followed by `RELEASE_MEM`.
The diagnostic's `ACQUIRE_MEM` is inside the IB. BO flushing defaults to zero;
the probe's ordinary CPU memory barriers do not themselves issue `CLFLUSH`.
These are source observations, not proof that a particular cache is stale.

The review used Linux v6.12, pinned to
`adc218676eef25575469234709c2d87185ca223a`, rather than a moving latest branch:

- [GFX11 ring implementation](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c):
  the compute IB's header, VALID/VMID fields and the selected 64-bit completion
  fence fields agree with the local encodings. This is not equivalence of the
  complete driver or initialization state.
- [IB scheduler](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ib.c):
  ring-level memory synchronization precedes IB emission when
  `AMDGPU_IB_FLAG_EMIT_MEM_SYNC` requests it. The call is conditional; its
  existence does not establish a missing mandatory prefix for every submission.
- [Packet definitions](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/nvd.h):
  the probe's `0xc381` includes its documented instruction/scalar/vector/L1/L2
  invalidation and L2 writeback fields. The upstream synchronization helper has
  additional GLM fields and a different high-size literal; these differences
  are not demonstrated fixes.

All three reviewed reference files carry MIT-style permission notices. Their
hashes and license review are recorded in the validation record. No upstream
implementation body or full header is copied. Existing component licenses,
shader notice and public-binary publication restrictions remain unchanged.

The source review did not establish a packet-encoding correction that explains
the observed mismatch. It therefore makes no production kernel, PTE, cache-mode
or fence change. An in-IB barrier's presence alone cannot show which bytes the
command processor fetched. The next diagnostic targets CPU-side publication
without changing GPU packet order or selecting a different IB address.

## Two policies, one narrow operation difference

`tools/native_ib_publication_probe.cpp` is separate from the frozen two-policy
tool. Its explicit CLI is:

```text
native-ib-publication-probe --check|--run-control|--run-ib-publish [--upper]
```

Both execution policies preserve the original reuse fixture: one context, one
16-KiB GTT BO, the same two pre-staged 320-byte IBs, the same shader and patterns,
and the same re-poisoned 1024-byte output at `0x2010`. Both dispatch slot 0 at
`0x1000` twice and rewrite it before the second dispatch. Slot 1 remains guarded
and is never submitted. Pass 0 is unchanged.

| Policy | Additional operations before pass 1 submission |
| --- | --- |
| `--run-control` | None |
| `--run-ib-publish` | `CLFLUSH` on the five aligned IB lines at BO offsets `0x1000`, `0x1040`, `0x1080`, `0x10c0`, `0x1100`, then `MFENCE` |

The operations follow the IB rewrite, output poisoning and existing CPU barrier,
and precede submission. They touch only the 320-byte rewritten IB, not the code,
inactive IB, output or whole BO. This is an investigation of targeted CPU cache
maintenance, not global BO flushing or a performance optimization.

Both modes require CLFLUSH capability and a reported 64-byte line size before
device enumeration. Unsupported capability/geometry is refused. The fixed
publication helper rejects null, unaligned and overflowing ranges before any
cache operation. Existing PCI identity, Darwin 25/x86_64, ABI 1.12/build34 and
queue-readiness admission remain. `--run`, `--run-reuse` and `--run-fresh` are
refused before device access. Check-only mode submits no GPU work and performs
no IB publication, but still opens the native client for identity/readiness.

Both modes retain zero/50,000-ns/two-second-capped waits, full 16-KiB comparison,
two-dispatch maximum, the 250-ms pause and original build34 exercise-failure
HOLD. An error cannot authorize another dispatch or claim success. The success
marker is specific to the CPU IB policy and excludes driver/display acceptance.

## Host validation and execution boundary

The fake-IOKit fixture executes the actual C++ diagnostic and independently
checks every publication address, exactly five operations, fence placement,
complete staged BO and submission order. CPU capability and CLFLUSH/MFENCE
operations are mocked. Injected CPU-publication, stale-IB-fetch and stale-output
models are separate assumptions; a model's policy-dependent result is not
hardware evidence or a cache/ISA simulation.

Run host-only validation from a clean committed checkout:

```sh
python3 -m unittest discover -s tests -p test_native_ib_publication_runner.py -v
python3 tools/test_native_ib_publication.py --out build/ib-publication-host-tests
```

On 2026-11-16, the clean source snapshot passed all 4,316 actual-C++ ASan/UBSan
scenarios: 1,079 distinct cases in each policy/VA combination. The completed
report was checked as the exact Cartesian set without duplicates. All 23
focused tests passed (nine canonical, seven previous freshness and seven new
publication tests), along with 48 actual-C++ ASan/UBSan regression scenarios
for the previous freshness tool. The real x86_64 IOKit/CoreFoundation build
passed with warnings treated as errors. Disassembly confirmed the architecture
primitives were compiled and test CPU hooks were absent; the binary was not run.

The existing manual source workflow adds this fake-CPU/fake-IOKit test only.
It does not execute the native tool or add its binary to public packaging.
The native framework build is compile-only, using the real architecture helper;
no native mode, including `--check`, was executed during offline preparation.
The compile-only recipe is:

```sh
mkdir -p build
clang++ -arch x86_64 -std=c++17 -Wall -Wextra -Werror \
  -I src/phxbringup -I tools/phxctl tools/native_ib_publication_probe.cpp \
  -framework IOKit -framework CoreFoundation \
  -o build/native-ib-publication-compile-only
```

Source hashes, exact case accounting and build evidence are in
[the validation record](validation/native-ib-publication-diagnostic-20261116.json).

Any future hardware comparison must first reproduce the control with this new
source/binary under independent containment, then use a separately bounded
publication-only scope with the same binary. Old consumed packets are not
controllers for this tool. No initializer, new runtime job, installation or
recovery is armed by this change. A passing publication trial would prioritize
CPU-side IB visibility, while still coupling cache writeback/invalidation with
the added fence and timing. It would not distinguish those effects or establish
a global cache policy. A failure would not prove that CPU visibility is correct
or justify changing packet bits.

Default retains A1/A2/corrected-A3 at `64f3d99`. Wait promotion and accelerated
desktop remain on HOLD. No GUI stability, FPS, two-second-cap wait or wait-fix
acceptance is claimed. Source rollback is a normal revert of this isolated
diagnostic addition; there is no installed driver change to undo.
