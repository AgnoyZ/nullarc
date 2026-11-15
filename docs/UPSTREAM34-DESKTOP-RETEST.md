# One original-build34 desktop acceleration reboot test

## Authorization and verified starting point

On 2026-11-15, after changing the default branch to original build 34 plus the
VRAM layout correction, the owner explicitly requested a reboot acceleration
test. This is a new bounded request; all prior consumed attempts remain closed.

Before preparing it, the completed original34-plus-correction headless receipts
were read and checked against the current boot. Both GPU queues wrote their
expected values and were adopted. The unchanged Metal probe completed on the
AMD GPU and verified a GPU-written value. Current loaded image, geometry and
the four corrected installed user files match their pinned identities. The
original kernel, accelerator, plugin, runtime, firmware and startup script are
unchanged. The complete EFI manifest was independently checked read-only and
left unchanged/unmounted. Observed OS: macOS **26.7.2 / 25G332**, x86_64.

The desktop is still using the firmware framebuffer at this checkpoint. The
earlier uncorrected original desktop attempt failed in CoreDisplay device
creation. The address correction does not establish that this separate display
failure is fixed; this trial measures that outcome once.

## Single new trial

The original startup daemon will execute on the next ordinary boot. The
one-boot `phxfb-boot` arming and original M2 marker select the original native
framebuffer. No kernel/runtime installation, EFI write, broad NVRAM reset,
security change, partition operation or same-boot reinitialization is included.
Only the specific original display-arming variable is set/cleared, with its
normal original commit operation.

A new external launchd witness observes the original startup. Its preparation
role has already run with zero target calls. It never invokes `full.sh`,
`bringup5.sh`, `mesboot` or `phxctl`; GPU initialization is performed only by the
unchanged original daemon, using the four corrected installed helpers/scripts.
The witness restores GPU-off after that daemon has crossed its kill-switch
gate, removes persistent rearming and does not retry a consumed desktop boot.

Limits are **one ordinary reboot/desktop attempt**, a **300-second independent
observation deadline**, one unchanged Metal probe, and at most **one managed
recovery reboot**. Upstream's own watchdogs/recovery behavior remain unchanged;
the external observer is not a prerequisite gate before upstream's first I/O,
and these software timers cannot guarantee recovery from a hard hardware hang.
An abandoned initial dispatch restores the safe flags rather than retrying.

Success requires the exact loaded build34 image, target geometry, successful
original queue/adoption/startup evidence, original Metal publication, real
GPU-written Metal output, the native framebuffer, increasing actual present
counter samples, correct display-arming state, a stable single WindowServer
and no new WindowServer diagnostic report. Startup text or device presence
alone cannot pass. Failure records its evidence, disables the next GPU/display
attempt and requests bounded recovery. A subsequent unexpected boot closes
the consumed scope instead of initializing again.

## Preparation evidence and status

The retained observer regression and new single-stage/admission/frame tests
passed **41 CPU methods**. They cover one-use transitions, stale or incomplete
prior evidence, exact watchdog ACK identity, output/publication failures,
restarted WindowServer, absent frame progress and recovery/expiry. These CPU
tests do not run GPU commands. A fresh root-owned packet verifies **417 inputs**,
and its actual launchd preparation role passed. The current four helper hashes
also match default source commit `5805c05bed6cf0ce1e3fc28f8d088f6e5e296993`'s
validation record.

At this public source checkpoint the trial is prepared but **not yet armed or
dispatched**. Exclusive private arming/reboot receipts and the actual next-boot
result must be read before reporting dispatch, desktop success or recovery.
The new authorization does not reopen any old packet.

Rollback is to preserve/restore the empty original GPU-off marker, remove the
original M2 marker and only the specific `phxfb-boot` display variable, then
verify a firmware-display boot if recovery was required. No driver replacement
is necessary. Raw logs, crash reports, identities and diagnostic archives remain
private; no binary publication is added.

## Consumed trial result: original startup requested fallback

The exclusive receipts and actual startup/kernel logs were read back on
2026-11-15. The single ordinary restart was dispatched successfully and
independently verified. Its native-desktop boot began at **18:29:35 +08:00**.
The observer recorded that original startup crossed its off-marker gate and
restored GPU-off while removing persistent display arming. There is no
desktop-complete, Metal-exit or trial-success receipt.

The original startup log reported `PhxAMDFB on the panel: 1`. Kernel logs also
show the native panel publication. All **17** fresh firmware load records have
zero transport and firmware statuses. However, startup retained no successful
compute/graphics queue or adoption output, then reported a selector **113**
transport/size failure and `M2 failed (NMXAccel did not start)`. The unchanged
upstream `m2_fail` path explicitly requested a fallback reboot. The external
witness did **not** dispatch a managed recovery reboot. Its next-boot closed
receipt preserves the consumed state and prevents retry.

The fallback boot began at **18:31:05 +08:00**. Independent reads confirmed
original build 34, the target geometry and all four installed corrected-helper
hashes. The firmware framebuffer is present; PhxAMDFB, NMXAccel and
IOAccelerator are absent. One WindowServer has remained on this boot. GPU-off
is an empty file, the M2 marker and pending marker are absent, and the specific
display-arming variable is absent. No new WindowServer/panic/kernel diagnostic
report was found in the checked system diagnostic directories after trial
start. That absence is not a general proof that no transient fault occurred.

Thus this attempt **did not establish accelerated desktop operation**, and
hardware acceleration is **not active on the fallback boot**. This does not
invalidate the separate 17:51 headless boot's real GPU/Metal execution success;
those successful consumed receipts remain unchanged.

Only the consumed external witness was retired: its exact plist was archived,
launchd confirmed the job had already exited/unregistered, its processes were
absent, and its auto-start plist was removed. Original startup and the installed
helpers were rehashed and left unchanged. All historical receipts remain
private and intact. No new GPU call, Metal probe or reboot was dispatched
during readback or retirement. The default source branch remains
`upstream34/vram-layout-fix` at
`5805c05bed6cf0ce1e3fc28f8d088f6e5e296993`.

## Diagnostic correction prepared offline; not deployed

The exact first post-firmware failure remains **unknown**. Original `full.sh`
discarded both streams from `bringup5.sh`, and the former wrapper omitted the
actual IOKit return code and returned lengths. Selector 113 invokes
`claimAccel`, which refuses a GPU that is not ready; its visible failure can
therefore be downstream of incomplete initialization. The retained data cannot
distinguish a power/autoload failure from another early initializer exit, and
does not establish a new CoreDisplay failure.

The downstream isolated build-34 recipe now preserves initializer stderr,
keeps PSP-destroy errors and firmware-load errors out of stdout suppression or
filtering, and propagates the exact initializer exit status before any later
queue commands. Transport diagnostics now include the actual return code and
expected/returned counts and byte lengths. Admission, GPU-command order,
fail-closed behavior, watchdog policy and original kernel/ABI remain unchanged.

Fourteen focused ASan/UBSan and synthetic-shell methods passed. They include
the retained geometry/order checks, error-versus-short-output diagnostics,
early initializer error retention, and no later queue operations after failure
in either watchdog mode. Native x86_64 helper compilation, ad-hoc signing and
strict verification also passed. These tests never link real IOKit into the
fixture or run a GPU command. The diagnostic candidate is source-only: it has
not replaced the installed four files or the default source branch, and no
new desktop attempt is armed. A future separately bounded trial must record
its exact inputs and retain these diagnostics from startup; consumed intents
must not be replayed.

## New diagnostic trial prepared after owner continuation

The owner's subsequent continuation requests the next deployment/test step.
A new isolated packet has been prepared; the failed 18:29 trial remains closed.
Its current-boot admission verifies that the earlier successful headless result
is historical evidence, and that the later failed desktop boot has a distinct,
closed fallback boot. It does not incorrectly require the accelerator to be
active on that fallback boot.

Only the four diagnostic user files have now been installed, backed up and
independently read back. Original build 34, accelerator, firmware, plugin,
runtime and startup remain unchanged. The complete EFI manifest was checked
read-only and left unchanged/unmounted. OS remains macOS 26.7.2 / 25G332.
The diagnostic wrappers additionally retain the command input and returned
status for ABI/firmware refusal, so a failing SMU message can be identified.
The successful GPU-command order and fail-closed rules are unchanged.

Preflight initially refused new Python bytecode caches created by a prior
inspection command that omitted its no-bytecode option. Exact comparison
found **53 added cache files**, zero removed files and zero modifications to
pre-existing pinned files. Only those exact additions were archived privately,
the original manifests were restored and independently rechecked, and all
subsequent frozen-interpreter commands use `-B -I -S`. No immutable manifest
was weakened or rewritten to admit the additions. Preflight completed before
the four-user-file installation.

Fourteen helper methods, native x86_64 compilation/signature checks and
**42** observer methods passed. The observer tests include saving the failing
startup block and declining a competing recovery request when upstream has
already requested fallback. The fresh actual launchd preparation role passed
with **zero GPU calls**; its contract verifies **2087** pinned inputs, including
the frozen interpreter files. This observer still does not gate upstream's
first hardware I/O.

At this source checkpoint the four diagnostic files are installed, GPU-off is
present, display arming is absent and **no reboot has been dispatched**. The
new packet permits one ordinary reboot/native-desktop attempt, a 300-second
independent observation deadline, at most one unchanged Metal probe after
startup succeeds, and at most one managed recovery reboot. Original startup
watchdogs remain unchanged. A detected original fallback is recorded without
immediately dispatching another shutdown; the independent deadline may still
recover the same boot if original recovery does not happen. Subsequent boots
close a consumed attempt instead of retrying. Software timers do not guarantee
recovery from a hard hardware hang.

Arming/dispatch and next-boot receipts must be independently read before
claiming that this new reboot happened or acceleration passed. The default
source branch remains pinned at `5805c05bed6cf0ce1e3fc28f8d088f6e5e296993`;
these diagnostic files are from the downstream isolated recipe. Rollback
restores only the four exact saved user files with GPU-off present and native
display arming absent. The prior root packets and their receipts remain intact.
