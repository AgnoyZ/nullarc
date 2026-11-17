# Build34 fixed-image desktop validation

On **2026-11-17**, after the owner requested desktop-takeover validation, the
exact compute-submit synchronization image passed a bounded native desktop
trial on macOS **26.7.2 / 25G332**. Independent read-back reparsed its GPU
outputs and all 30 frame samples, then verified recovery and retired the
single-use jobs. **The machine finishes running the restored original
build34 image, GPU off, on the firmware framebuffer.** Persistent accelerated
desktop adoption remains on HOLD.

This extends the [native compute comparison](BUILD34-SUBMIT-MEMSYNC.md).
It does not prove long-duration stability, resolve the earlier WindowServer
watchdog's cause, measure input latency or FPS, or validate the newer plugin
sources and PR28 publication wait.

## Exact image and retained runtime

The default source checkpoint was
`62d695424072522b5c05779fe500baec5a73aad5`. The reused signed PhxBringup image
has SHA-256
`7c2f8d4d68b63f32fba120f60fec0877e1e58607e70253c94d7394883f7cf8e1`;
its complete driver source is byte-identical to the integrated source, SHA-256
`fffd2bdfea25ca87312679e194949f2538807b43610d157f06c9dde0d33a70d0`.
It retains build marker 34 and the original ABI, but its loaded identity remains
distinct from the original image. Original-only diagnostic admission was not
broadened, and neither withdrawn build was used.

To isolate the kernel change, both scopes retained the installed A1 plugin,
the existing A2/corrected-A3 accelerator and the pinned RADV/translator/runtime
files. The plugin executable SHA-256 is
`a056873d7c3a83b910c0fc6e65cfc4bcc825993cf49d3d821fd69f794a1b9f08`.
The exact loaded accelerator identity was checked, and a new Metal process
verified the target PCI device and its actual loaded plugin image. The
additional plugin PRs and PR28 sources on the default branch were **not
installed for this trial**; no PR28 wait opt-in was set. This is acceptance
of the fixed kernel with that retained runtime, not every component of the
current default source tree.

Both scopes used the same signed native probe, SHA-256
`f89035937656ecc16cf6329a24801e29b8cd40d3c646e66d03628b358a9703a5`,
with `--run-single`. The same Metal/IOSurface probe was used in both scopes,
SHA-256 `cb313747fcc669c485a9d026bf37e0bb5d48b0a60bc22af54a80aa7d2de1065c`.
Its timeout/error path retains uncertain GPU resources until recovery,
instead of killing the client or unwinding its command/resources. The probe
compiled and signed as x86_64 without warnings; it installs no runtime.

## Single-use execution and first observer refusal

Each fresh root-owned packet allowed one initialization, one native probe
with at most two dispatches, one Metal probe with three commands, one initial
boot and at most one managed recovery reboot. No consumed packet was replayed
and no automatic retry was configured. An independent process enforced a
105-second pre-release deadline and a 300-second overall deadline. The
Metal probe had a 15-second completion bound per command and a 55-second
outer bound; uncertain GPU clients were retained for recovery.

A temporary one-boot startup wrapper prevented concurrent execution of the
ordinary initializer. The production startup scripts remained unchanged.
The disk driver and original startup job were restored before GPU execution;
the exact fixed loaded image was then checked independently. The controller
ran the original compute/graphics initialization and adoption order, verified
the native IB output, and only then claimed the accelerator and followed the
original display-arming sysctl order and values. The GPU-off marker remained
present throughout, and no persistent M2 marker was created. The existing
one-shot framebuffer NVRAM arming was used and consumed; this was not an
NVRAM reset, boot-argument change or security-setting change.

The first scope passed its **65 CPU methods**, 18 credential-dropped
WindowServer file-access checks, compute/graphics queue checks, both complete
native IB arena checks and all three Metal commands. A read-only WindowServer
mapping capture contained both the plugin and RADV. The observer then refused
acceptance because it additionally required a WindowServer
`IOUserClientCreator` property below the accelerator. That property is not
promised by the driver source. The assertion prevented the frame observation
from completing; it is not evidence that a GPU command or the desktop failed.
The first scope recovered and retired with no new matching diagnostic report.
Its unsuccessful observation is retained rather than relabelled as a pass.

Only after independent exact restoration and retirement was a distinct second
packet prepared. The observer now records that creator property as optional
diagnostic data while retaining mandatory WindowServer plugin/RADV mappings,
real GPU output, native framebuffer, frame progress and stable compositor
checks. Tests cover absent, mismatched and matching creator properties and
still reject missing images or multiple compositors. A bounded first-present
readiness phase also avoids treating a sample taken immediately after busy-hold
release as a completed desktop observation. Exceptions retain a private
traceback. The driver, runtime, probes and display parameters did not change.
The revised packet passed **67 CPU methods** and all 18 access checks.

## Second-scope hardware result

The exact fixed image loaded and the original image was restored to disk
before initialization. Original compute and graphics results and both queue
adoptions passed. Both native dispatches then verified their complete 16-KiB
arenas with no mismatch. The Metal probe completed one render and two sampler
commands, sampling IOSurface slots 0 and 15: **32 pixels / 128 channels** all
matched. This exercises bounded graphics and compute execution through the
retained runtime; it is not a general Vulkan conformance result.

The native framebuffer and accelerator were active, the firmware framebuffer
was absent, and the busy hold was released. Read-only mappings of the single
WindowServer process contained the pinned plugin and RADV. No creator property
was exposed by that accelerator query; its absence did not replace any
mandatory execution or frame-progress check.

Across **30 samples spanning 151.303705558 seconds**:

| Observation | Start | End |
| --- | ---: | ---: |
| Successful present transactions | 42 | 12,666 |
| Failed transactions | 0 | 0 |
| Copy-skipped transactions | 0 | 0 |
| Synthetic VBL ticks | 3,681 | 21,835 |

All 29 adjacent sample pairs had increasing present and synthetic-VBL counters,
the same single WindowServer, and unchanged armed/hold state. No new matching
WindowServer/kernel/GPU diagnostic report appeared. The observer's elapsed
interval including its final checks was 156.114793389 seconds. The transaction
and synthetic-VBL counters are **not physical scanout, game FPS or a measured
input-latency result**.

Read-only panel properties stayed at **2560 by 1600 / 120,000 milliHz** with
validated timing, totals 2720 by 1694 and estimated pixel clock 552,921,600 Hz.
The clock estimate was checked against those totals; it is not a physical
clock measurement, mode change or direct live timing-callback test.

## Independent recovery and disposition

After the bounded observation, one managed recovery restored the exact
pre-test startup job and allowlist, verified the original disk driver and
rebooted. Independent read-back reparsed the native output, Metal output,
WindowServer mappings and all frame samples before accepting the result.
Both scopes' dedicated, manifest-checked nine-file EFI recovery subtrees were
removed only after restoration. Each consumed job was retired.

Final independent read-back verified all **347 original EFI files**, all
**46 protected files**, protected links, security state and kernel collections.
The exact original image is loaded, the fixed image is absent from the running
kernel, GPU-off is present and only the firmware framebuffer is active. No
trial job, GPU client, held process or recovery scheduler remains; EFI is
unmounted and no subsequent GPU task is armed. No Windows EFI/configuration,
partition, BIOS, OS security or boot arguments were changed, and no raw
diagnostic or binary was published. The Windows fallback script was not run
in Windows and is not claimed runtime-validated.

The result is **bounded desktop takeover passed with the fixed build34 kernel
and retained installed runtime, independently recovered**. Persistent daily
adoption, longer interactive/background-load stability, sleep/wake, FPS and
PR28's real GPU wait remain separate, unaccepted items. The earlier watchdog
and first observer refusal remain in the record. Sanitized evidence is in
[`validation/build34-desktop-hardware-20261117.json`](validation/build34-desktop-hardware-20261117.json).

## Subsequent 30-minute low-load observation

After the complete bounded PR28 real-GPU wait packet passed and was independently
recovered, a fresh single-use scope based on default
`654e62fac841db5bd3ab3b93d0c5f281847151e8` extended desktop observation to
1800 seconds. It retained the exact compute-sync build34 kernel and release
PR28 plugin from that accepted packet. The wait policy stayed default-off,
WindowServer remained excluded, and only the admission probe opted in inside
its own process. Build41/build42 were not candidates.

The new packet passed **73 CPU/controller methods**, both CPU observer
self-checks and all **18 runtime-access checks**. Its single initialization
passed compute, graphics and both queue adoptions. Both native dispatches
verified their full 16-KiB arenas. The same bounded Metal admission workloads
passed: three successful publication waits, a genuine buffer-only fast path,
and a controlled 1 ms timeout followed by real completion and verified pixels.
No production driver, plugin, runtime or display parameter was changed for
the longer observation. Recovery instructions were corrected to name this
new scope's exact dedicated subtree; the Windows fallback was not executed.

The independent guardian retained the 105-second pre-release bound and used
a **2100-second overall bound**. Observation sampled at nominal five-second
intervals and refused any interval over 30 seconds. No synthetic stress or
FPS workload was injected. The measured sample span was
**1802.062185442 seconds**, with **336 samples / 335 validated intervals** and
a maximum interval of **5.726472353 seconds**. The controller's elapsed
observation including its final checks was 1809.486080748 seconds.

| Observation | Start | End |
| --- | ---: | ---: |
| Successful present transactions | 840 | 72,718 |
| Failed transactions | 0 | 0 |
| Copy-skipped transactions | 0 | 0 |
| Synthetic VBL ticks | 5,863 | 141,346 |

Every adjacent pair had increasing present and synthetic-VBL counters, the
same single WindowServer and unchanged armed/hold state. Panel timing stayed
at 2560 by 1600 / 120,000 milliHz, and no new matching diagnostic report
appeared. These counters establish progress; they are not FPS or measured
input latency.

Automatic recovery completed without restoration errors. Independent review
reparsed the native and Metal output, WindowServer mappings, every sample
and every incremental sample receipt. It confirmed the exact original loaded
kernel and complete original plugin, all 46 protected files and 347 original
EFI files, unchanged links/security/kernel collections, GPU-off and only the
firmware framebuffer. The nine exact recovery files, restore-only job and
candidate plugin stage were removed; no test client, held process, recovery
scheduler or follow-up GPU task remained, and EFI was unmounted.

**The bounded 30-minute low-load desktop observation passed.** This is not
unrestricted long-term stability, background-load or interactive-stutter
acceptance, sleep/wake validation, a camera result, permanent desktop adoption
or FPS acceptance. The earlier watchdog and unresolved first PR28 failure
remain historical evidence. FPS is the next separate stage and had not
started at the final readback. Sanitized results are in
[`validation/build34-desktop-stability-20261117.json`](validation/build34-desktop-stability-20261117.json).
