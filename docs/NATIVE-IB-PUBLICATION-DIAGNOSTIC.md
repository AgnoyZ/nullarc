# Selective CPU IB publication diagnostic

Status on 2026-11-16: **one bounded hardware trial per policy completed; both
failed pass 1 output integrity**. Selective IB `CLFLUSH` plus `MFENCE` did not
eliminate the mismatch; it is not adopted as a production fix. The earlier
[paired trial](NATIVE-IB-FRESHNESS-DIAGNOSTIC.md#original-build34-fresh-comparison)
failed its reused/rewritten IB policy and passed its immutable fresh-slot policy.
That comparison motivated this narrower test; neither pair establishes a
production cache defect. All four policy scopes are consumed and may not be
replayed.

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
command processor fetched. This diagnostic targets CPU-side publication
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
primitives were compiled and test CPU hooks were absent; that offline
compile-only binary was not run.

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

## Original build34 hardware comparison

The later hardware pair ran on macOS 26.7.2, build `25G332`, using the same exact
loaded original build34 executable. A separate runtime binary was built from
clean committed source `4724ee5833e846e96340d224028acd71041c0c93`; the original
offline compile-only binary remained unexecuted. Both policies used that same
new runtime executable, SHA256
`2dafa897c7df387e098c647d3628958c2edf5fcc6bd146c3da0b3a02fb73d70f`,
with identical source/header hashes, fixture and zero BO-flush settings.

The new `control` ran first and reproduced the earlier failure signature.
Independent result, retirement and final recovery checks completed before the
separate `ib-publish` scope was prepared. Each scope allowed one original
initialization, at most two low-VA dispatches and one recovery reboot; neither
scope could launch a subsequent GPU trial.

| Policy, one trial each | Pass 0 | Pass 1 | Wait durations, in call order |
| --- | --- | --- | --- |
| `control`: rewrite/reuse slot 0 | Full 16-KiB comparison passed | Positive retirement, then `0xde` instead of `0xdf` at `0x2010` | 3,506 / 17,533 / 8,606 ns |
| `ib-publish`: same slot, plus five IB-only flushes and fence | Full 16-KiB comparison passed | Positive retirement, then the same `0xde` instead of `0xdf` at `0x2010` | 7,524 / 21,730 / 9,357 / 13,224 ns |

Both scopes passed original compute/graphics output and queue-adoption checks.
Both reached the second dispatch, retained resources immediately on validation
failure, and completed their one recovery. The recovery observers made zero
GPU calls. Independent checks confirmed 347 EFI files (including 148 Microsoft
files), 46 protected files, two links and security/kernel collections unchanged,
with no new matching diagnostic reports. Both consumed startup jobs were
removed. Final readback confirmed GPU-off, the firmware framebuffer, and no
active probe or shutdown process. No driver installation, EFI replacement,
tuning write or preliminary reboot occurred.

The publication path is bound by the exact source, policy argument and second
dispatch; its CPU instructions/cache effects were not separately instrumented
on hardware. The treatment flushed only the rewritten IB, not shader, output,
inactive IB or the whole BO. Its negative result does **not** prove CPU
visibility correct or identify GPU cache/prefetch, address reuse or execution/
fence ordering as the cause. One trial per policy across separate initialization
and boot scopes is not a statistical study. It provides no basis for adopting
global cache flushing or changing PM4 bits.

See the [new-source control record](validation/upstream34-native-ib-publication-control-20261116.json)
and [publication treatment record](validation/upstream34-native-ib-publication-trial-20261116.json).
The treatment record binds the exact control record hash. The earlier
reuse/fresh records and offline validation record remain unchanged. Neither
new scope exercised a two-second-cap wait, CPU load, concurrent clients, GUI
responsiveness or FPS. No further hardware scope is armed; neither consumed
packet may be replayed. Further source investigation must precede another
separately bounded experiment.

Default retains A1/A2/corrected-A3 at `64f3d99`. Wait promotion and accelerated
desktop remain on HOLD. No GUI stability, FPS, two-second-cap wait or wait-fix
acceptance is claimed. Source rollback is a normal revert of this isolated
diagnostic addition; there is no installed driver change to undo.
