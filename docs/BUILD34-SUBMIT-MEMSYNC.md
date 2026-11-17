# Build34 compute-submit synchronization

Status on 2026-11-17: **the exact outer-ACQUIRE image passed both guarded
native single-IB dispatches, independently recovered and retired; the
byte-identical driver source is integrated on the default branch**. The
fresh original and equal-footprint NOP controls both failed the second
dispatch at `0x2010` (`0xde` instead of `0xdf`). This is bounded native
compute evidence for the minimal change, not desktop, full Vulkan, graphics,
long-run stability or FPS acceptance. A later separate
[desktop trial](BUILD34-DESKTOP-VALIDATION.md) passed bounded graphics/Metal
output and about 151 seconds of desktop frame observation with the retained
installed runtime, then recovered. Persistent adoption, newer plugin/PR28
GPU validation, long-run stability and FPS remain unaccepted.

The approved parent source checkpoint remains
`64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c` with A1/A2/corrected-A3. The
additional kernel change has exactly two sites in `gpuSubmit`:

1. Reserve eight extra dwords when the actual selected queue is compute,
   preserving the original 16-dword guard and lock order.
2. After successful `vmBind`, emit the eight-dword ACQUIRE_MEM prefix before
   all user IB descriptors on that compute queue. The packet is
   `c0065800 00000000 ffffffff 00ffffff 00000000 00000000 0000000a 0000c3b1`.

No user descriptor, sequence, RELEASE_MEM, history, WPTR publication, CPU
flush, doorbell, wait, ABI, VMID choice, helper, initializer, metadata or
graphics-queue behavior is changed. RELEASE_MEM remains last. No immutable
tail or 256-dword padding is added. As documented in the
[source preparation](BUILD34-OUTER-MEMSYNC.md), the Linux v6.12 comparison is
a conditional outer-ring synchronization reference, not a claim that this
reproduces its full VM/submission machinery or proves a particular cache
fault.

## Hardware comparison and exact identity

The [fresh original/NOP comparison](BUILD34-OUTER-NOP-HARDWARE.md) completed
and retired before the separate ACQUIRE route. Its exact failing probe
outputs were independently reparsed again before preparing and activating
ACQUIRE. The new controller refuses missing retirement/recovery, a different
probe/source/mismatch, contaminated arena, a successful NOP control, or new
matching diagnostic reports. Old frozen scopes were not modified or replayed.

| Image | Signed executable SHA-256 | Complete arena checks passed |
| --- | --- | --- |
| Original build34 | `4a88035fd2ead990b8c44b638c9283d579b14d6ba4f0b48d78d6435a3a44a412` | 1 of 2; exact original fault |
| Eight-dword NOP prefix | `3124e6378ef7d3c7c04ec84aa69a724e67f70c2e5ab8c3cc00ed45b50b81d543` | 1 of 2; same fault |
| Eight-dword ACQUIRE prefix | `7c2f8d4d68b63f32fba120f60fec0877e1e58607e70253c94d7394883f7cf8e1` | 2 of 2; no mismatch |

All used the same signed `--run-single` probe, SHA-256
`f89035937656ecc16cf6329a24801e29b8cd40d3c646e66d03628b358a9703a5`,
on macOS **26.7.2 / 25G332**. The ACQUIRE scope pinned preparation commit
`e9751c8f443f9bcb8b9ef5ccacdb205b26d59dac`; its parent differs from the
control preparation only in documentation. Each scope had one initializer,
one probe client, at most two submissions, an independent 300-second deadline,
one recovery reboot and no retry. ACQUIRE startup first restored the original
image to disk, then passed independent exact loaded-identity, disk-backup,
protected-state and GPU-off checks before any initialization.

Both rewritten same-address IB executions passed their complete 16-KiB
arena checks. Independent output parsing after recovery confirmed native
completion and both checks; no held process, mismatch or controller exception
occurred in the ACQUIRE scope. The original and NOP failures remain recorded.
The equal footprint controls against attributing this result solely to eight
extra ring words; it does not prove a microarchitectural root cause or a
general performance improvement.

The integrated complete `PhxBringup.cpp` SHA-256 is
`fffd2bdfea25ca87312679e194949f2538807b43610d157f06c9dde0d33a70d0`,
identical to the reviewed source that produced the exact hardware-tested
image. The integrated function SHA-256 is
`12fcaa4cb7ab0a19df9ac16491e7654362547625e4fbe879840cbfb9d351e722`.
Build marker 34 is unchanged, but original and modified image identities
remain distinct: **original34 admission is not broadened to admit this fix**.

## Source regression and original diagnostic boundaries

`tools/upstream34_layout/submit_memsync.py` verifies the entire current
protected input set against the approved checkpoint plus only the exact
tested driver transform. It compiles the actual integrated function into the
existing independent packet/accounting fixture. ASan/UBSan passed **36,111**
CPU scenarios, including all IB counts and starting residues, actual adopted
1024-dword compute-ring geometry, fallback queues, capacity refusal, history
reuse and final-fence accounting. It links no IOKit and models no GPU cache,
DMA, MMIO or hardware completion. Six new integration methods and 46 affected
historical transformation/admission methods passed. The new CPU target is
included in the existing macOS CI job.
The prefix consumes real ring space: the preparation fixture refused 298
cases for either prefix versus 292 for original, reflecting small-ring
capacity differences. The actual adopted 1024-dword ring still fits all 64
IB descriptors plus prefix, final fence and the unchanged guard.

The 20 original layout methods, five general CPU test programs, A1 sampler,
A2 surface-key, A3 descriptor-mask, four plugin PR methods and ten publication
wait methods also passed. A3 initially failed to compile because the local
Vulkan include path was missing; rerunning with the existing reviewed header
checkout passed all three modes, 321 cases each. No SPIR-V file fixture was
supplied. General firmware-fixture cases were skipped because their fixtures
were absent; synthetic firmware cases passed. These are CPU regressions,
not additional GPU, firmware or desktop trials.

Historical original34 diagnostic/build recipes retain their exact original
source/hash admission and therefore refuse the now-modified default source.
Their unit tests use the immutable approved Git object or a temporary exact
original-source fixture; the production tree is not reset. No old recipe,
CPU report or consumed hardware scope is silently retargeted to the fix.
Use a separate checkout of its documented preparation checkpoint when
reproducing a historical offline recipe. For the integrated function use a
fresh private destination:

```sh
nice -n 15 /usr/sbin/taskpolicy -b python3 -B -m unittest discover \
  -s tests -p test_upstream34_submit_memsync.py -v
nice -n 15 /usr/sbin/taskpolicy -b python3 -B \
  tools/upstream34_layout/submit_memsync.py --out build/fresh-integrated-submit-CPU-private
```

## Recovery and limits

The new ACQUIRE route passed 43 CPU swap/startup/prerequisite/EFI-lock tests;
the candidate controller passed another 24. An audit found that the earlier
unused Windows fallback script filtered a historical recovery directory
instead of that trial's dedicated directory. The new script uses its exact
ACQUIRE directory and has a regression check. Neither Windows script has
been executed in Windows, so this is only a source correction, not fallback
runtime validation.

After the ACQUIRE recovery reboot, independent read-back verified original34
loaded, fixed image absent, GPU off and firmware framebuffer only. The
consumed test job and restore-only job were removed. Only the manifest-checked
nine-file dedicated recovery subtree was deleted; a separate verification
matched all **347** original EFI files and **46** protected files, protected
links, security settings and kernel collections. No new matching diagnostic
report or remaining trial job/client/held process was found. EFI was unmounted.

**The machine finishes this trial running the restored original image, not
the integrated source fix.** Installing a persistent fixed build, another GPU
scope, full-runtime testing and desktop adoption remain separate operations;
no task is armed by this record. No Windows EFI/configuration, partition,
NVRAM, BIOS or security setting was changed, and no binary/raw diagnostic was
published. Build41/build42 were not used. The
[aggregate hardware/integration record](validation/build34-submit-memsync-20261117.json)
preserves the exact bounded result and these limits.
