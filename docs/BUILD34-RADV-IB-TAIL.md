# Original34 real RADV IB-tail experiment

Status on 2026-11-17: the explicit compute-only source workaround passed a
bounded real-hardware comparison through the real Mesa submission path. The
same binary's single-IB control reproduced the exact second-dispatch fault;
the separately recovered tail scope passed both whole-arena checks. This is
bounded transport evidence, not full RADV/Vulkan runtime acceptance. The
production policy remains opt-in; default waits, accelerated desktop and FPS
claims remain on HOLD.

## Evidence motivating this change

The [same-binary descriptor-order diagnostic](BUILD34-IB-PREAMBLE-DIAGNOSTIC.md#same-binary-single-versus-nop-tail-hardware-result)
reproduced the exact second-dispatch wrong value at `0x2010` (`0xde` versus
`0xdf`) with one IB, and passed both whole-16-KiB checks with dispatch followed
by an immutable NOP IB. Both scopes independently recovered and retired. That
result establishes a bounded diagnostic difference. It does not prove a CP
cache root cause, test real RADV submission, or establish a desktop fix.

## Minimal production-path adaptation

The [scoped Mesa patch](../mesa-patches-build34/0001-radv-original34-immutable-ib-tail.patch)
changes only `ac_darwin_kext.c`, `ac_darwin_kext.h` and `ac_darwin_drm.c`:

* A new shared core can explicitly enable `RADV_DARWIN_BUILD34_IB_TAIL=1`.
  Absence or `0` preserves the existing submission policy. Other strings are
  refused; WindowServer is excluded. The choice is fixed before sharing a core.
* The same core VA manager reserves a private 4-KiB low-canonical range. A GTT
  BO is checked for size/domain/placement, filled once with the reviewed
  eight-dword NOP, and CPU-unmapped before its read/execute GPU mapping is
  published. Neither the address nor the BO is supplied by an application IB.
* Each native submit carries at most 63 payload IBs and one immutable tail.
  Payload order/bytes are preserved. Only the last block receives the user
  fence; only the final successful sequence is published to the caller. The
  whole plan is checked for compute engine/instance/ring before the first block.
* Enabled split transactions are serialized. An error, malformed reply, zero,
  sentinel or non-increasing sequence makes the connection's submit state
  permanently uncertain. Later work is refused; accepted chunks are not replayed.
* The private BO and reservation live with the connection, shared by all its
  Mesa devices. There is no disable/reconfigure/early-free interface. Before
  closing an enabled connection that submitted work, one bounded retirement
  wait is checked. Uncertainty, errors, busy or invalid retirement enter HOLD
  and retain the connection for independent recovery. This does not add
  close-time quarantine to the original kernel or protect against killing a
  held process. Do not kill it or use process exit as GPU recovery.

The helper separately requires original build34, ABI 1.12, VMID 8, 64 IBs,
GFX11.0.1 and native/S1B readiness without HUNG. It does not change the
kernel's admission or fabricate a build identity. Only compute submissions
are admitted by this explicit experiment; graphics/SDMA are not validated.
The original34 kernel, ABI, production `tools/phxctl`, A1/A2/corrected-A3 and
existing licences/notices are unchanged.

The destructor's bounded wait and error HOLD belong solely to the explicit
experiment. They do not promote the default native wait policy. The mutex
resource is created with the connection, but disabled submits retain their
original 64-IB block sizes and fence behavior.

## Reproducible source and licence review

The matching Mesa source was reconstructed from the already verified RADV-only
source package; it is not a kernel candidate. Mesa commit
`f5cb8ee032adabef599ae892ec4e42d796b84da9`, Cobalt64 commit
`d6c9aedf8e6526a39e349b5886cbc8c7ddf77f65`, Phoenix/nullarc commit
`8aba872560a3c9b7dc7a0ddebfad001c6dddf315`: nine Cobalt Mesa patches, seven
Phoenix Mesa patches, then the three native-Phoenix-only/command-buffer-cleanup/
bounded-allocation-diagnostics source patches recorded in that package.

| Source archive | SHA256 |
| --- | --- |
| `mesa-base.tar.gz` | `b66b7e4b8a5a6a9049e0266209f6f719895777932f2cbcd5eeb7bcbbfd47767d` |
| `cobalt-radv.tar.gz` | `96779ff15b1a8660f1521ee6ac1a2ce39c40dd51ed7f878a4873345ea9999684` |
| `phoenix-radv.tar.gz` | `09871aecb7291ec5393f2afd67b4dc9f379f2b0b17bbd13cb7d9e6a8ce854b19` |
| `nullarc-radv.tar.gz` | `65a284c778ea84f01186d93ea4062cffc6196f9a91867ea34395f30a19b3ab13` |

All 19 patch hashes were checked against package provenance before application;
the three reconstructed transport files matched the independently extracted
runtime source byte for byte. A first private reconstruction attempt stopped
at `git apply --check`: nested-repo cwd semantics had skipped earlier patches.
It is not successful evidence. The corrected reconstruction used an isolated
source repository and verified the resulting blobs. The public recipe likewise
creates an isolated staging repository and verifies that all three files changed.

The transport/core/sync sources identify as MIT. The Google 2023 canned-device
and Google 2024 sync-provider notices, the MIT libdrm allocator/list notices,
DRM UAPI notices, AMD shader notice and Mesa licence file remain with the frozen
dependency sources. Only these reviewed source components are compiled into
the probe. No PolyForm plugin, firmware or new binary is copied into the public
tree. The full-stack artifact block and the separate kext/RADV artifact scopes
remain unchanged; this source recipe publishes no binary artifact.

## CPU checks and compilation

Use the [staging and test commands](../mesa-patches-build34/README.md) with fresh
ignored output paths. Recipes verify the 30 pinned source/dependency hashes,
approved original34 protected sources, and that inputs do not change during
preparation. Native compilation freezes all non-SDK dependencies, rejects
unfrozen include dependencies, signs and checks x86_64 without execution.

The CPU suite compiles the actual patched marshaller under ASan/UBSan. It
checks 1,028 combinations of 1–257 payload IBs, default/tail policies and
fence/no-fence, exact descriptor bytes, untouched return values on failure,
strict admission, one-time NOP publication and two concurrent split callers.
Eleven separate CPU subprocesses establish HOLD on partial/uncertain submission
and invalid retirement without closing. Only these fake processes are then
terminated by the test harness.

The real shared-core and VA allocator lifecycle is also executed: shared
connection ownership, reservation exclusion, teardown ordering, exact opt-in,
WindowServer exclusion and initialization failures. Vendored libdrm's legacy
`container_of` spells its offset using a null member expression and trips
UBSan even on the disabled baseline. The CPU allocator build uses its supported
macro override with compiler `offsetof`; no sanitizer is disabled and neither
production source nor native compilation is changed by that test override.

The original Mesa test has 134 assertions. Its eight historical non-Phoenix
service-selection assertions already fail on the pinned native-only baseline.
The suite requires the exact same eight failures on baseline and patched
source, with no additional failures; it counts only the 126 unchanged passing
checks. They are not presented as an all-green upstream test.

Finally, the actual new probe is linked to real core/CS/sync/VA functions with
fake IOKit. Fault injection covers single/tail policies, admission, rejected
withdrawn identities, allocation/context shape, submit/wait errors, stale pass-0
bytes and corruption of shader, rewritten IB, unused slot, staged NOP and guard
regions. Its CPU output oracle is not a GPU ISA or coherency simulation.

The final 2026-11-17 run passed 5,752,346 transport assertions across those
1,028 split/fence combinations, 210 real-core/allocator assertions, 11 isolated
HOLD cases, both concurrent callers and 68 actual-probe CPU cases. All 20
original34 layout regression methods passed without skips. The frozen native
probe compiled, was signed and verified as x86_64, without execution. See the
[sanitized offline record](validation/build34-radv-ib-tail-offline-20261117.json).

## Separate native comparison and rollback

The signed probe takes `--check`, `--run-single` or `--run-tail`. It performs no
initialization. A single direct PCI-verified `1002:1900` client, strict original34
identity and Darwin 25 x86_64 are mandatory. Inherited RADV overrides are refused.
The real core reserves the tail; both modes request the same deterministic
payload VA and stage the same 16-KiB arena. Each pass submits one DRM IB chunk
through `acd_ioctl`, the real plan parser and the actual transport function.
The dispatch address is rewritten only before pass 1. The arena's NOP at
`0x1400` remains guarded and is never passed as a payload IB. Only the actual
workaround can add the separately owned tail BO.

After each dispatch the existing zero/50-microsecond/capped wait sequence must
establish positive retirement before the full arena is compared. Any uncertain
execution, malformed response or mismatch enters HOLD. The platform boundary
also caps native submissions at two and refuses close without retirement.

First run a **fresh single-IB control with this binary**. Only its exact fault
and independently verified recovery/retirement can admit a separate tail scope
with the same source and binary. A passing control stops this comparison.
Each scope independently needs a new GPU-off boot, original image/protected
files/EFI/security pins, a live independent deadline, at most one initialization,
one client, two dispatches and one recovery reboot. Old scopes stay consumed.
No automatic retries, driver deployment, EFI/NVRAM/security changes or desktop
takeover are part of this source addition. Rollback is the independent recovery
to GPU-off/firmware framebuffer; no persistent runtime file is changed by the
probe. A native transport pass would still not be a Vulkan/graphics/desktop or
FPS validation.

## Real transport hardware comparison on 2026-11-17

Both fresh scopes used source
`7cd4b6c605d96d7af1128eab98428542bea560a0` and the identical signed probe
SHA256 `9e73ce02a2e7502249bed4e191b455638d42c75086bdb514dd815b2f8b7e1fd2`
on macOS 26.7.2 (`25G332`), with the exact original34 kernel image. The
previous offline record remains a preparation-time snapshot; the
[separate hardware record](validation/build34-radv-ib-tail-hardware-20261117.json)
records subsequent execution and recovery.

| Policy | Dispatch 1 | Dispatch 2 after same-address IB rewrite | Independent recovery |
| --- | --- | --- | --- |
| Single IB, workaround disabled | Full 16 KiB passed | `0x2010`: `0xde`, expected `0xdf` | Passed; held client retained until reboot |
| Separate immutable NOP tail enabled | Full 16 KiB passed | Full 16 KiB passed | Passed; test job removed |

Each scope separately performed one original initialization, then opened one
executing native client for at most two dispatches. There was no additional
`--check` client, retry, proxy fallback or second initialization. The second
scope was admitted only after the first precisely reproduced the fault and
its recovery and retirement were independently verified. Tail ownership,
submission and retirement used the actual patched Mesa core, VA manager,
CS parser, marshaller and sync code; only platform open/map/call were supplied
by the probe's strict direct IOKit adapter.

Both dispatches in each scope reached positive retirement before arena
comparison. Neither required the two-second capped wait. The longest observed
wait syscall wall time was 19,717 ns for single and 35,036 ns for tail; these
are timing observations, not GPU execution times or frame-rate measurements.
The control detected the mismatch despite positive retirement, so faster fence
completion alone is not the acceptance criterion.

Each scope recovered once to GPU-off and firmware framebuffer, with zero GPU
calls on its recovery boot. Independent read-back verified 46 protected files,
two protected links, 347 EFI files including 148 Microsoft files, unchanged
security/KC pins and no new matching crash/watchdog reports. Both consumed
launch jobs were removed. No driver or runtime was installed by this comparison.

The evidence verifies the bounded compute transport workaround for the exact
reproducer. It does not establish the cache/root cause or validate repeated
workloads, concurrent GPU clients, complete Vulkan, graphics or desktop use.
Adding a descriptor still changes submission footprint and timing. A full
runtime build/integration check and separately scoped execution evidence remain
necessary before broader promotion. Original34 still lacks close-time
quarantine; forced exit of a held GPU process remains unsafe. All earlier
hardware packets remain consumed.
