# Explicit native desktop queue handoff

Status, 2026-11-14: **build 39 loaded; the original desktop diagnostic stopped
at queue-selection readback and its one-attempt authorization is consumed**.
See the [observed reboot result](
DESKTOP-DEPLOYMENT-ADMISSION.md#observed-reboot-result-and-recovery).
This supplies concrete `mesboot desktop-init` and
`mesboot desktop-claim` interfaces for the [startup coordinator](
ALLOCATION-STARTUP-COORDINATOR.md). It does not establish a working desktop
or the cause of the earlier allocation refusals. The later [terminal selector
preflight](DESKTOP-SELECTOR-PREFLIGHT.md) is an uninstalled, unexecuted source
addition; historical build-37 and Phase A evidence remains unchanged.

## Native sequence

Both commands require four GART arguments (virtual base, mapped bytes, table
offset, default-page offset), followed by four arena/doorbell-index pairs in
the order KIQ, scheduler, compute, graphics. Every invocation derives physical
and MC addresses from the opened driver. Experiment environment variables
are refused before service lookup. Legacy command layout gates remain intact.

`desktop-init` uses one connection throughout these stages:

1. Check the strict pre-adoption bootstrap snapshot and all complete resource
   extents. Reserve the exact layout through the new privileged selector 117
   before register or VRAM activity.
2. Refuse an active MES pipe or selected hardware queue. Check doorbell/CP
   setup readbacks, then use the existing checked explicit GART and MES paths
   on the same connection. Their active-state refusals remain intact.
3. Clear all owned arenas, initialize KIQ and scheduler with checked HQD
   readbacks, and verify scheduler resource/query completions. The new KIQ
   path programs a 4 KiB queue size matching its ring/MQD; it does not inherit
   the legacy KIQ experiment's size value.
4. Add compute and graphics separately through MES. Each checks its own HQD,
   fresh scratch/memory markers and a new full-width RELEASE_MEM completion
   token. Graphics includes the complete existing 960-dword clear-state
   preamble. Neither helper individually adopts a queue on this path.
5. Seal only after both engines pass. The provider independently checks both
   full-width tokens and writeback pointers before invoking the existing
   checked adoption method for compute and then graphics. Every refusal
   propagates; there is no output filter or implicit successful final command.

The resulting pointers are 16 compute dwords and 976 graphics dwords. These
values describe this versioned packet sequence, not a change to the legacy
six-scalar adoption ABI. `desktop-claim` supplies the identical layout and
positions to selector 117. It does not use the reference-layout claim path
or reinterpret a GPU-active bootstrap snapshot as pre-initialization evidence.
The provider permits one claim from a sealed reservation and retains the
build-38 both-engine claim guard.

## Ownership and failure lifetime

`PhxDesktopHandoff.h` defines the shared fixed-size wire contract and validates
all GART/PSP separations, four arena extents and distinct bounded doorbells.
KIQ and scheduler each own 16 KiB, compute owns 24 KiB, and graphics owns
32 KiB. These include MQD, EOP, result/test, clear-state and fence storage,
in addition to rings/writebacks. No reservation is inferred from a late
aggregate activity bit.

A provider-wide debug mutation lock serializes reserve with the complete
debug mutation lane. Before reservation, legacy commands retain their
existing semantics. During initialization, only its owning native client can
write registers, VRAM or doorbells; PSP reconfiguration, raw firmware commands,
debug system-memory replacement and legacy adoption/claim are refused. Reads,
allocation capture and ordinary native submission do not acquire this lock.
After sealing, all raw debug mutations remain refused, including writes by
the original initializer. The exact sealed claim is a separate operation.

Closing an incomplete initializer abandons its reservation. Failed completion,
adoption or claim retains the reservation; there is no reset, release, rearm
or reclaim API. Successful sealing transfers lifetime to the provider, so
initializer exit does not free the backing arenas. Stop retains the existing
quarantine policy and explicitly includes any desktop reservation. A failed
second adoption can leave the first queue retained; it cannot claim the full
accelerator or authorize reuse. The reservation protects software producer
ownership. It cannot prove device quiescence or recover a hard bus/kernel hang.

## Verification and remaining delivery work

`tests/test_desktop_handoff.py` compiles the complete actual native CLI with
fake IOKit and separately extracts the actual provider reserve/seal/gate,
adoption, readiness, claim and bootstrap methods into an ASan/UBSan CPU
harness. The fakes supply observations; they do not emulate or establish GPU
execution. Tests cover relocated/reference layouts, complete packet/address
checks, marker/fence failures for either engine, transport failures, ownership,
aliasing, abandonment, partial adoption and single-use claim. The manual
allocation-contract workflow includes this suite without target access or
artifact upload.

Native compile/link and clean committed-source validation are recorded in
[the validation record](validation/desktop-native-handoff-20261114.json).
Those source-stage checks did not supply native acceptance or an installed
startup packet. The concrete caller had to deliver the complete pinned kernel/helper
closure, checked firmware/power stage, display/release/monitor/disarm adapters,
startup rollback and same-boot historical hold/panel evidence. Preserve the
120-second hold and existing three-reports-in-90-seconds monitor policy.
Source tests did not consume the owner's diagnostic attempt; the later
hardware attempt did. The [execution plan](ALLOCATION-EXECUTION-PLAN.md) remains
the integration boundary.

The later [concrete adapters](DESKTOP-STARTUP-ADAPTERS.md) compose these commands
with checked firmware/power, display, release, monitoring and independent
recovery, and add retained hold/server history. Its subsequent private delivery
and failed target attempt are recorded in the observed reboot result above.

For source rollback, revert this candidate as a normal new commit, retaining
the build-38 claim guard and build-37 diagnostic history. No installed rollback
was required for that source milestone. Do not run these commands against
an inherited already-initialized boot or substitute the old installed helper.

## Historical source-stage verification, 2026-11-14

A final clean isolated committed snapshot passed **589 full-suite tests** on
Python 3.13.18 in 310.084 seconds, with zero skips. All tracked input hashes were
unchanged. Apple Python 3.9.6 separately passed all **19 native handoff CPU
test methods**; the final actual cleanup/stop harness passed **115 cases**,
including three desktop-reservation quarantine cases. The passive-close
regression executes the actual client cleanup while the fake initializer lock
is already held.

The same production inputs compiled and linked PhxBringup build 39, mesboot
and phxctl on Apple Clang 21.0.0 with host SDK 26.5. All 1,232 pinned
MacKernelSDK files matched before and after compilation. Each binary passed
x86_64 architecture and strict ad-hoc signature verification. Existing
compiler warnings and earlier rejected validation runs are recorded separately;
no hosted CI pass is inferred. These private binaries were neither installed
nor executed against a target, and no binary artifact was uploaded.
