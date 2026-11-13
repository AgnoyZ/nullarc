# Allocation refusal kernel diagnostic, build 36

This source-only candidate follows the failed build-35 desktop attempt recorded
in [the RADV result](RADV-CLEANUP-CANDIDATE.md#diagnostic-desktop-refusal-captured-and-firmware-fallback-restored-2026-11-13).
It is diagnostic instrumentation, not an allocation or desktop repair. It has
not been installed or run on the target. The installed kernel remains build 35.
The previous one-shot authorization is spent.

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
the kernel source is unchanged by this CI correction. A fresh run is required
before claiming the complete hosted check passed.

## Next evidence required

A future, separately authorized collection needs candidate/source identity,
the precise failing boot and process/image correlation, and a bounded capture
of both `PhxAlloc: v1` and the installed RADV's native diagnostics, preserving
the existing fallback. A fresh deployment/recovery plan must precede any
installation or new M2 attempt. This source change does not authorize one.

Validated-but-incomplete sequences alone cannot distinguish ordinary in-flight
work from a hang. Repeated bounded observations and progress evidence would be
needed. A prepare-stage protection error would establish the failing kernel
stage, but would not explain the host pages' permissions or origin. The full
desktop root cause remains unresolved; increasing allocation budgets or
weakening the mutation/pinning guards is not justified by current evidence.
