# Allocation refusal kernel diagnostic, build 36

The later [build-37 software snapshot candidate](ALLOCATION-SNAPSHOT-CANDIDATE.md)
adds a bounded evidence channel that does not rely on IOLog persistence. It is
uninstalled and does not change the hardware findings below.

This diagnostic candidate follows the failed build-35 desktop attempt recorded
in [the RADV result](RADV-CLEANUP-CANDIDATE.md#diagnostic-desktop-refusal-captured-and-firmware-fallback-restored-2026-11-13).
It is diagnostic instrumentation, not an allocation or desktop repair. Build 36
passed the first firmware-framebuffer boot and exact loaded-image verification
under fresh owner authorization, then completed its single authorized M2
reproduction. That reproduction failed and the existing monitor restored the
firmware desktop. Native refusal codes persisted, but the new kernel diagnostic
records did not appear in the retained capture. The full cause remains
unresolved. Both the earlier and this build-36 one-shot M2 grants are spent.

## Observation contract

`PhxBringup.cpp` emits bounded `PhxAlloc: v1` kernel messages at three existing
refusal sites. The native results, budgets, pin direction, cleanup and VM
mutation gates retain their existing behavior. There is no new completion wait,
Busy retry, device operation or relaxed protection.

| Operation/site | Reason or stage | Meaning |
| --- | --- | --- |
| `vmMap` / `vmUnmap` idle guard | `retirement-pending` | The queue observations validated, but conservative global retirement is below the context's last submitted sequence. |
| `vmMap` / `vmUnmap` idle guard | `retirement-invalid` | Retirement could not validate its observation and returned its conservative zero. |
| `doGemVa` MAP overlap | `pending-overlap` | An existing pending mapping overlaps the requested range. |
| `doBoImportHost` | `stage=descriptor` | `withAddressRange` returned null; the original `kIOReturnNoMemory` is returned. |
| `doBoImportHost` | `stage=prepare` | The descriptor's `prepare()` returned the recorded original code; the descriptor is released and no BO/budget/output is published. |

The guard record contains `last` (context sequence), `submitted` (global
sequence), and the exact `retired` result used to refuse mutation. Each queue
has `reason`, `read`, `done`, `floor`, `count` and `pending` fields: validator
reason, whether the fence was read, observed fence value, software retirement
floor, outstanding history count, and first incomplete sequence. `pending=0`
means no incomplete sequence was selected for that queue, not that all history
was validated. The separate reason and read fields must be checked first.

Both the decision and diagnostic use the same fence read while holding the
existing GPU lock. Logging never reads a fence again. An invalid first queue
preserves the existing early return; the second queue remains `unobserved`.
An inactive queue is also `unobserved` in the retirement record because it was
skipped. Do not interpret this as proof that either queue completed work.

Validator reasons are `valid`, `missing-output`, `no-aperture`, `inactive`,
`unaligned-fence`, `history-overflow`, `future-floor`, `all-ones-fence`,
`regressed-fence`, `future-fence`, `zero-sequence`, `nonmonotonic-sequence`,
`future-sequence`, and `unknown-fence`. `unobserved` is the initialized state.
Rejected fence values are observations only; they are never accepted as
completion or copied into the normal completion output parameter.

Four records are allowed per context, operation (map/unmap), and guard class
(pending/invalid). The counters reset when a context is allocated to a new
client, under the same GPU lock. Pending-overlap, descriptor failure and prepare
failure each have a separate four-record budget per native client, protected
by its existing dispatcher lock. Counters saturate rather than wrapping.
There is no new user ABI, sysctl or global log-reset control.

`GPU_UNMAP` in a guard record includes existing pending-map cleanup calls to
`vmUnmap`, including those made by the reaper before another selector executes.
It is a kernel operation label, not proof of an external UNMAP request. These
calls share the context's UNMAP sampling budget. Kernel and RADV samples must
not be counted as one-to-one events. No request identifiers, handles, host/GPU
virtual addresses, physical addresses, pointers, page contents or machine
identifiers are emitted. Import and overlap records include byte size; imports
also state the unchanged `direction=inout` requirement.

## CPU validation and native compilation

`tools/test_allocation_diagnostic.py` extracts the actual working-tree methods
and state declarations, compiles CPU harnesses with address/undefined
sanitizers, and records input and fragment hashes. Its 43 cases cover both Busy
guard classes, cross-queue retirement, early invalid return, exactly one fence
read per queue, pending overlap, later completion, failure cleanup, independent
and saturated sampling budgets, every validator rejection reason, raw Mach 2,
unknown preparation codes, successful import and silent success/precheck paths.

The existing BO retirement, queue retirement, context retirement, VM binding,
page-walk/cleanup and import harnesses also exercise the changed methods. The
context reallocation case checks that a previous client's exhausted counters
do not carry over. These use explicit OS and device fakes. They do not prove
real page permissions, kernel logging persistence, GPU progress or desktop
liveness. Bounded logging may still perturb timing on a real target.

Local validation on 2026-11-13 used Python 3.12.16. All 417 Python tests and
43 focused diagnostic cases passed. The actual-source regression checks also
passed 82 BO-retirement, 86 queue-retirement, 112 context-retirement, 71 VM
binding and 30 BO-create/import cases with address/undefined sanitizers.
The focused cross-queue case uses distinct global submission sequences: one
queue has completed sequence 5 while the other still has sequence 3 pending,
so conservative retirement remains 2. This is a synthetic contract check,
not an observation of the failed desktop's queues.

The normal source-test job includes the new harness. The manual
`kernel-compile-check.yml` workflow builds only PhxBringup on
`macos-15-intel` using the already pinned MacKernelSDK, verifies x86_64 and its
ad-hoc signature, and uploads no artifacts. No local native driver build is
part of this work. A passing hosted compile would still not establish that
the target accepts or runs the candidate.

The first hosted run, `43443404094` at source commit `c89dd0a`, passed the
43 focused CPU cases and compiled, linked and signed PhxBringup. It then failed
because the new `lipo -verify_arch` invocation placed the input file after the
architecture list. The workflow was corrected to put the input file first;
the kernel source is unchanged by this CI correction.

The corrected hosted run **`43444215578`** passed at commit `ec7a26f` on
`macos-15-intel`: all 43 focused CPU cases, PhxBringup
compilation/linking, strict ad-hoc signature validation, x86_64 verification,
and the source-cleanliness check. The run's artifact count is zero. It did not
load a target kernel or execute GPU work.

The Ubuntu `source-tests` job `131945953357` in run `43443224639`, at kernel
source commit `c89dd0a`, also passed its complete source-test matrix, including
all 33 check stages, the 417 Python tests and new diagnostic harness. The local
replay stopped after 31 successful stages once that complete hosted matrix had
passed; the remaining two duplicate long shader simulations are not local
passes. This was not a test failure. The automatic full-stack
runs for this change and its CI-only correction were cancelled to use
the scoped PhxBringup check instead. Those cancellations are not full-stack
build passes. Earlier runs were left untouched. No full-stack or desktop
acceptance is claimed.

## Retained diagnostic package and read-only preparation

The existing owner-authorized, manual two-kext workflow completed successfully
in run **`43446700859`**, job `131957914403`, at exact source commit
`3948e122d6ae26fa0644a70838bc0bfb76d91752` on `macos-15-intel`. It retained
one seven-day artifact under the scope in [KEXT-PROVENANCE.md](KEXT-PROVENANCE.md).
The downloaded package SHA-256 is
`890b64e65d12bd62e4cd098ec5dd7581b39d2b0aa64131b32ac40c2840db3575`;
its PhxBringup executable SHA-256 is
`3ac7816a80504bf587d3c684c0941e12dd6c686c2d8f48e3dcff093fdd2b176b`.

Independent local inspection verified the GitHub artifact digest, outer and
inner checksums, both strict ad-hoc signatures, x86_64 Mach-O types, all 85
exported project source files against the pinned commit, and all 1,226 SDK
source blobs against the pinned SDK Git tree. The PhxBringup executable contains
the expected allocation diagnostic strings. These checks inspected binary
structure and provenance; they did not load or execute either kext.

Read-only target checks on 2026-11-13 confirmed build 35 on macOS 26.7.2
(`25G332`), M2 off and the firmware framebuffer present. Installed runtime,
plugin, startup and recovery inputs match the previous verified state, apart
from the expected per-boot generated address log. A read-only EFI inspection
verified all 334 current files and a fresh complete backup, then unmounted the
partition; the older 331-file backup was also verified. Neither backup is a
tested independent bootable recovery medium.

A fresh private deployment, collection and rollback plan is prepared. Only
PhxBringup is a proposed replacement: the native ABI header and PhxAccel source
tree are unchanged from the installed build-35 source, and the packaged
PhxAccel is not proposed for installation. The plan first requires a verified
build-36 firmware boot, then at most one fresh M2 collection with the existing
fallback. Package preparation alone did not authorize installation, restarts or
M2 execution. No driver replacement, GPU call, M2 arming or restart scheduling
was performed during that preparation phase.

## Owner-authorized staging and first firmware restart

On 2026-11-13 the owner explicitly authorized replacement of PhxBringup only,
a first normal restart with M2 off to verify build 36, and one later M2
reproduction after that readiness check. The two normal restarts retain the
three-minute delay and existing failure fallback; no automatic second M2
attempt is authorized.

Fresh live preflight passed. The new staging helper also passed six isolated
file-operation checks: successful replacement, staging collision, candidate
byte mismatch, staging signature failure, active signature failure, and a
failed stage-to-active rename. The failure cases preserved the old active
bundle and unrelated test files. These are file-safety checks, not GPU tests.

At 23:06:54 +0800 the exact packaged build-36 PhxBringup was staged on the
identity-checked EFI. The complete 334-file current backup was verified; build
35 was retained on the EFI, all 331 unrelated EFI files and the OpenCore config
were unchanged, and the partition was unmounted. Independent live readback at
23:07:20 +0800 verified the candidate, retained build 35, complete resulting
EFI manifest, and unchanged runtime, startup and recovery inputs. No PhxAccel,
auxiliary kernel collection, runtime, plugin, firmware or startup helper was
replaced. The running kernel was still build 35, M2 remained off and no GPU
command or initializer was replayed.

At this staging checkpoint the first firmware-framebuffer restart was the next
authorized phase. Candidate loading, its exact loaded image, completed startup
and preserved runtime/recovery state were required before preparing the fresh
one-shot M2 executor. The later M2 phase was not armed or automatically scheduled
by staging. Neither a successful copy nor the existing software fallback proves
recovery from a kernel or bus hang.

## Verified build-36 firmware boot; one M2 attempt prepared

The first restart produced a new boot at 23:14:01 +0800 on 2026-11-13.
Administrator readback at 23:23:19 +0800 verified actual build 36 on macOS
26.7.2 (`25G332`) and its exact loaded Mach-O identity against the hosted
package, not just a version property or staged file. The firmware framebuffer
was present, PhxAMDFB absent, display gates zero, M2 NVRAM and markers absent,
and the existing once-per-boot startup had completed. Runtime, plugin, retained
originals, startup and recovery inputs were verified, including the expected
new per-boot address log. A fresh read-only EFI inspection verified the complete
resulting manifest, candidate and retained build 35, then unmounted it.

Read-only preparation at 23:25:43 +0800 found no new WindowServer reports since
that boot. A bounded 11.71-minute query for both allocation prefixes found zero
verified kernel and zero verified RADV diagnostic records; one collector audit
row was excluded. No additional GPU test or initializer was invoked. This
proves a real candidate load and inherited startup on the firmware desktop,
not M2 acceptance, allocation correctness or diagnostic persistence on failure.
The root cause remains unresolved.

The fresh one-shot M2 executor and bounded postboot collector are prepared
under the already-granted owner authorization. Seven isolated guard checks
passed: successful arming, preflight refusal, existing grant consumption,
post-arming failure, a competing scheduler, post-scheduling failure, and log
classification excluding audit/wrong-image/wrong-path/wrong-process or wrong
boot records. These checks used fake NVRAM and schedulers; no real GPU, NVRAM or
restart was invoked by them, and the unrelated fake scheduler was never
cancelled. The existing grant is claimed exclusively before mutation to prevent
replay across attempt directories. Fresh live preflight also passed with build
36 and M2 still off. Actual arming, restart and postboot results require their
separate receipts; none is established by these preparation checks.

## Single build-36 M2 outcome and firmware fallback

The executor armed the one-shot at 23:33:06 +0800 on 2026-11-13; independent
readback completed at 23:33:31. The uniquely identified shutdown announced the
second normal restart for 23:36:06. The existing startup ran with PhxAMDFB at
23:36:33, adopted its queues and released the display at 23:36:42. Its monitor
subsequently reported three WindowServer crashes or hangs and requested the
existing fallback reboot. No initializer was manually replayed.

Collection completed at 23:42:12. The original window ran from 23:33:05 to
23:41:59, within its fifteen-minute bound. Its 124 raw rows include both the
M2 and fallback boots and the collector's own audit row; those are not a single
failure population. Exact sender-image UUID/path, boot and process grouping
identified 37 RADV diagnostic samples, all on the failed M2 boot:

| Operation | Samples | Original native result |
| --- | ---: | --- |
| GPU_MAP | 15 | `0xe00002d5`, Busy |
| GPU_UNMAP | 10 | `0xe00002d5`, Busy |
| BO_IMPORT_HOST | 12 | raw `0x00000002`, Mach protection failure |

WindowServer accounts for 35 samples across four process lifetimes. Dock and
SecurityAgent account for one MAP refusal each. The first WindowServer reached
the per-process eight-sample cap for each operation; these are sampled records,
not total failures or unique allocation requests. Later plugin messages also
recorded command-buffer allocation returning `VkResult -2` and refused imported
host pointers. A nearby plugin import message can follow a MAP failure as well
as a host-import failure, so adjacency does not identify the native stage.
There are no request IDs establishing one-to-one correspondence.

Three new WindowServer reports were parsed using their JSON headers and bodies,
capture times, boot identities, PIDs and loaded images. All belong to this M2
boot and contain the expected RADV and plugin image identities. Crash reports
redact the RADV directory; its exact path and UUID are independently present
in the same boot/PID's unified records. The first
faulted in `nvlog` called by `nvmtl_vk_cmd_begin`, with repeated SkyLight
`RenderEncoder`/`SetScissor` frames and a stack-guard protection exception. This
does not establish a defect in `nvlog`, nor is that exception the same event as
a native host-import protection refusal. The other two reports aborted through
CoreDisplay's `RunFullDisplayPipe` assertion path. Their capture times, rather
than the later report filenames, were used for correlation. These stacks show
failure consequences; they do not identify the queue-retirement branch.

The new boot time is 23:37:53; startup history records PhxAMDFB absent and normal
completion at 23:38:10. Kernel logs independently record the absent one-shot
and retained firmware framebuffer on this fallback boot. Readbacks at 23:41:56
and 23:50:55 verified build 36 and its exact packaged loaded Mach-O identity,
IONDRVFramebuffer present, PhxAMDFB absent, zero display gates, no M2 NVRAM or
markers, no pending shutdown/GPU helper and completed startup. Fixed runtime,
plugin, driver, startup and recovery inputs, the full retained EFI backup and
EFI identity/unmounted state passed verification. Only the expected generated
per-boot address log differs. This fallback result is not desktop-acceleration
acceptance or proof of recovery from a hard kernel/bus hang.

### Kernel observation gap

The primary capture contains zero verified `PhxAlloc: v1` records. A separate
81-second query spanning the failing boot used case-insensitive diagnostic
prefixes without sender restrictions and found no allocation diagnostic under
another attribution. Another query removed all message-prefix restrictions:
17,794 raw kernel rows became 8,743 after explicit timestamp, boot and process
filtering. None matched the candidate UUID, sender path or diagnostic prefix.
The 128 empty-message rows came from AppleACPIPlatform and IONVMeFamily, not the
candidate. Query stderr was empty. The current-boot circular dmesg and bounded
system.log check also yielded no candidate diagnostics; current dmesg cannot
reconstruct the failed boot. An empty capture is not an idle/completed queue.

The candidate's binary still contains its diagnostic format strings in
`__TEXT,__cstring` and imports `IOLog`. Source-only review of Apple's public
XNU revision `f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`,
`iokit/Kernel/IOLib.cpp` and `libkern/os/log.c`, found an additional possible
observation failure: IOLog forwards the format and caller to unified logging;
dynamic/fileset image resolution can reject an unresolved format address,
non-text format or mismatched caller image before storing a unified record.
This public revision has not been matched to the installed kernel, and no
per-image resolution failure was measured on the target. It is a logging
hypothesis to test, not an established explanation for the missing records.
Repeatedly querying the same absent records cannot recover the missing fence
observations.

Within the reviewed driver source, UNMAP Busy leads to the retirement guard;
MAP Busy additionally permits pending overlap. The raw import code is consistent
with a propagated `prepare()` failure, rather than the explicit budget or
descriptor-allocation results. Those are source-path deductions, not captured
kernel stage records. This attempt cannot distinguish `retirement-pending`
from `retirement-invalid`, read either queue's fence/progress values, or prove
the host pages' origin and permissions. It does not establish VRAM exhaustion.

The 43 actual-source CPU diagnostic cases were rerun with address/undefined
sanitizers after collection and all passed. They do not validate target log
persistence. No kernel source, installed binary, logging configuration, startup
helper or recovery policy was changed by this follow-up. The sanitized record
is [the build-36 postboot result](validation/allocation-kernel-build36-postboot-20261113.json).

### Independent model review, 2026-11-14

At the owner's request, Claude Code reviewed a sanitized evidence/source packet,
then completed a short corrective review. Its tools, MCP servers and hooks were
disabled. The initial response was incomplete, and both responses contained
material factual errors: they invented observed pending/prepare-stage records
despite the empty kernel capture, confused submission-time VMID binding with
MAP, or overread recovery as evidence of undamaged hardware. Those claims were
rejected against the retained logs and actual source. A proposed physical-segment
probe before preparing pageable memory was also rejected; the SDK requires this
virtual-range descriptor to be prepared before extracting its backing data.

The useful source lead remains the API boundary: the existing VM guard can
return Busy while retirement is below a context's last sequence; the Darwin
GEM_VA wrapper does not wait/retry it, and RADV maps the VA failure to device
memory failure. That source chain does not establish which branch occurred on
the target. Neither model agreement nor its proposed page-permission diagnosis
adds the missing fence, stage or page-origin observations. No reviewer proposal
was installed or executed against the GPU.

## Next evidence required

Before another target reproduction, prepare and validate an observation path
that does not depend solely on post-reboot unified-log persistence: retain
bounded kernel messages while the failing boot is still running, or expose a
bounded diagnostic snapshot for a passive collector. A proposed collector must
be reviewed against the unchanged fallback and must prove that the candidate's
records are readable; successful CPU formatting is insufficient. No new helper
has been installed and no global logging/security setting was changed here.
Any later installation or real M2 reproduction needs a new concrete execution
scope; the completed one-shot must not be replayed or expanded into a retry.

Validated-but-incomplete sequences alone cannot distinguish ordinary in-flight
work from a hang. Repeated bounded observations and progress evidence would be
needed. A prepare-stage protection error would establish the failing kernel
stage, but would not explain the host pages' permissions or origin. The full
desktop root cause remains unresolved; increasing allocation budgets or
weakening the mutation/pinning guards is not justified by current evidence.
