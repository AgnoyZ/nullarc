# Original34 outer-ring memory-sync experiment

Preparation checkpoint on 2026-11-17: **CPU checks and two private native
builds passed; neither image was installed or GPU-tested at that checkpoint**.
The subsequent [fresh original/NOP hardware comparison](BUILD34-OUTER-NOP-HARDWARE.md)
reproduced the same second-dispatch wrong value in both scopes; independent
recovery and retirement completed. NOP is rejected as a repair. This meets
only the reproduction prerequisite for a separate ACQUIRE comparison; the
ACQUIRE image remained uninstalled and untested at that checkpoint. The later
[separate ACQUIRE trial and source integration](BUILD34-SUBMIT-MEMSYNC.md)
passed both guarded native dispatches and independent recovery. Its exact
source is now integrated on default build34; desktop/wait/FPS HOLDs remain.
The preceding
[padding candidate failed on hardware](BUILD34-RING-PADDING-HARDWARE.md).
The unmodified original image retains the fault. A1/A2/corrected-A3,
helper/ABI, waits and desktop policy remain unchanged by the integrated fix.

## Source lead and its limits

Upstream `luuumi-dev/nullarc` main was checked again at
`8aba872560a3c9b7dc7a0ddebfad001c6dddf315`. The original34 submission function
has no outer-ring ACQUIRE_MEM. It explicitly refuses the native IB
`EMIT_MEM_SYNC` flag. The existing probe has an ACQUIRE_MEM inside the payload
IB; that position is different from a packet before the ring's IB descriptors.
Moving the same idea outside command memory is a hypothesis, not proof that
the CP fetched stale bytes or that a particular GPU cache is responsible.

The comparison reference is Linux **v6.12**, immutable commit
`adc218676eef25575469234709c2d87185ca223a`, not a claim about the latest kernel:

- [`amdgpu_ib_schedule`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/amdgpu_ib.c#L206)
  conditionally calls `emit_mem_sync` when the first IB carries
  `AMDGPU_IB_FLAG_EMIT_MEM_SYNC`, before its later IB emission loop. The
  allocator also sets this flag for its allocated IB. This is not a claim that
  every Linux userspace submission always receives this synchronization.
- [`gfx_v11_0_emit_mem_sync`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L6526)
  emits eight dwords: `c0065800 00000000 ffffffff 00ffffff 00000000 00000000
  0000000a 0000c3b1`. The compute ring function table exposes that callback.
- [`nvd.h`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/nvd.h#L269)
  defines GLI, GLM, GLK, GLV, GL1 and GL2 controls used in `0xc3b1`.

The downloaded MIT permission notices and exact reference hashes remain with
the private references. No Linux implementation is copied into production.
The source transform and test fixture are independent MIT-option project
tooling. Native builds reuse the previously audited pinned MacKernelSDK and
retain its notices; no firmware, plugin, runtime or binary is published.
Existing licences/notices are unchanged.

## Two edits, three CPU policies

`tools/upstream34_layout/outer_memsync.py` extracts the exact original34
`gpuSubmit`, with the existing complete-source and function hash admission.
It runs three separate CPU programs: untouched original, eight-dword NOP
prefix, and eight-dword ACQUIRE prefix. Both experiments change only:

1. Compute ring reservation gains eight dwords, with the original 16-dword
   guard. It is independent of WPTR, so the original lock ordering remains.
2. After successful `vmBind`, eight literal packet dwords are inserted in the
   outer compute ring before **all** user IB descriptors. Graphics emits no
   prefix, including when requests fall back to the other actual queue type.

NOP is one eight-dword Packet3 NOP: `c0061000` and seven zero payload words.
The ACQUIRE policy has the Linux-reviewed encoding above. The two policies
have equal footprints and identical accounting. No extra IB descriptor,
immutable tail, 256-dword padding, wait, output rewrite, VMID/TLB change or
completion shortcut is added. User IB descriptors and the entire sequence/
RELEASE_MEM/history/WPTR/flush/doorbell suffix remain unchanged. RELEASE_MEM
is still last. This does not replicate all Linux submission/VM synchronization
or prove that ACQUIRE prevents speculative IB fetch.

The CPU fixture checks exact prefix and descriptor words, zero graphics
changes, admission/refusal, all 64 IB counts, all 256 starting residues,
representative ring/counter boundaries, delayed CPU-injected retirement,
history exhaustion, fallback queues, WB/doorbell values and 70 successive
submits each at one and 64 IBs. ASan/UBSan passed **36,111 scenarios per
policy, 108,333 total**, without IOKit linkage. NOP and ACQUIRE each refused
298 scenarios versus original's 292: the extra prefix can exhaust a small
ring. Both fit the actual empty 1024-dword ring with initial WPTR 8, including
the maximum descriptor count. No GPU cache, prefetch, DMA, MMIO or completion
is simulated. Sixteen new Python regression methods and 16 existing shared
builder regression methods passed; these are CPU evidence only.

## Separate private images

`outer_memsync_candidate.py` accepts only the two pinned complete-source
hashes, a matching three-policy CPU report and unchanged tested recipes.
It uses the existing SDK archive/metadata/Mach-O validation helpers and the
original build script in a fresh private snapshot. Build source, SDK files,
toolchain, recipes and CPU report are checked around compilation. The output
PCI-match restriction matches the exact original control's complete plist;
the production plist is unchanged. Each candidate has a distinct private
Mach-O identity; version/build marker 34 alone is never admission.

| Policy | Complete driver source SHA-256 | Signed executable SHA-256 |
| --- | --- | --- |
| NOP prefix | `5c010ac379266cd7ac47292d5037e586baef50479a92286a5c6357b836de04d1` | `3124e6378ef7d3c7c04ec84aa69a724e67f70c2e5ab8c3cc00ed45b50b81d543` |
| ACQUIRE prefix | `fffd2bdfea25ca87312679e194949f2538807b43610d157f06c9dde0d33a70d0` | `7c2f8d4d68b63f32fba120f60fec0877e1e58607e70253c94d7394883f7cf8e1` |

Both serial low-priority native builds, ad-hoc signatures, strict signature
and x86_64 checks passed. Independent privileged read-back checked exact
source/binary pins, original-equal complete plist and identities distinct
from each other and the loaded original. Both retained only the same three
field-shadow warnings previously compared with untouched original34; no new
warning message was introduced. At the preparation checkpoint neither
candidate was installed or loaded, and original34 remained loaded with
GPU-off. See the
[aggregate preparation record](validation/build34-outer-memsync-preparation-20261117.json).

```sh
nice -n 15 /usr/sbin/taskpolicy -b python3 -B -m unittest discover \
  -s tests -p 'test_upstream34_outer_memsync*.py' -v
nice -n 15 /usr/sbin/taskpolicy -b python3 -B \
  tools/upstream34_layout/outer_memsync.py --out build/fresh-outer-sync-CPU-private
nice -n 15 /usr/sbin/taskpolicy -b python3 -B \
  tools/upstream34_layout/outer_memsync_candidate.py --policy nop-prefix \
  --CPU-record build/fresh-outer-sync-CPU-private/report.json \
  --sdk /path/to/reviewed/MacKernelSDK --out build/fresh-outer-NOP-private
```

## Hardware comparison boundary

Before any trial, freeze new exact-image controllers, review the owner-approved
internal-disk rollback route and fix the preceding trial's observer mount race
using shared serialization. Old consumed packets must remain unchanged and
must not be rearmed. Preserve the exact original image's admission checks.

Use the existing signed `--run-single` probe unchanged in fresh independent
scopes, with one initializer/client, at most two native submits, independent
300-second deadline, one recovery reboot and no automatic retry per scope:

1. A fresh exact-original control must reproduce the exact second-pass fault,
   then independently recover and retire before a changed-image scope.
2. Test the exact NOP-prefix image first. A success would show that the prefix
   alone changes the result; do not credit ACQUIRE or automatically proceed
   to its treatment. A different mismatch/timeout is failure/HOLD.
3. Only after a NOP-prefix scope reproduces the precise original failure and
   independently recovers/retires may a separate exact ACQUIRE-prefix scope
   test the equal-footprint synchronization hypothesis.

Candidate boots must restore the original disk image before GPU initialization,
then pass independent loaded-identity/disk/GPU-off checks. Both whole-arena
dispatch checks and native sequence/fence observations are required for a
bounded pass. Retain any mismatch/held process until recovery; never kill the
held GPU client. Restore original34/GPU-off and independently retire each scope.
Preparation does not adopt source or establish hardware acceptance. A bounded
compute pass alone does not establish desktop, graphics, stability or FPS
acceptance. The later exact-source integration has separate identity checks,
host regressions and the scoped hardware record linked above; it leaves those
HOLDs intact. The subsequent NOP comparison
completed steps 1 and 2 with the precise original failure; its consumed tasks
were retired and do not authorize replay. No hardware task is armed here.
