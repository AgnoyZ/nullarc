# Build34 R3 initial queue ownership

Status: source review only. No old-writer drain is proved on gfx1103/macOS,
no new MMIO or firmware operations were run, and the native reader remains
unbound. This is a prerequisite to reusing bootstrap and fence storage.

## What Linux establishes

The reference is Linux v6.12 at
`adc218676eef25575469234709c2d87185ca223a`, also used by the
[fence reader review](BUILD34-FENCE-READER.md). This is a read-only review of
the linked Linux driver code; no source or binaries were imported.

| Pinned reference | Relevant behavior | Limit for build34 |
| --- | --- | --- |
| [`mes_v11_0_unmap_legacy_queue`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/mes_v11_0.c#L446-L474) | The queue removal request identifies the legacy queue and waits for MES command completion. The preempt-without-unmap action is separate and supplies a trailing fence. | Needs a functioning scheduler the driver already owns and a known queue identity. Do not submit this through an unknown inherited scheduler or treat the preempt-only action as removal. |
| [`mes_v11_0_kiq_dequeue` and `mes_v11_0_kiq_hw_fini`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/mes_v11_0.c#L1310-L1425) | The driver holds `srbm_mutex` over the indexed register sequence and restores selection. For an active HQD it requests dequeue and polls the active bit before clearing doorbell and pointer state. The teardown wrapper separately disables MES. | The dequeue helper returns `void`; on poll exhaustion it still clears control/pointer state. That sequence does not provide build34 with a positive drain acknowledgment. |
| [`mes_v11_0_reset_queue_mmio`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/mes_v11_0.c#L337-L400) | The targeted reset has separate GFX and Compute sequences and returns a timeout if the selected HQD does not deactivate. | This is a better model for timeout propagation, but it still acts on a known queue and checks deactivation only. It does not prove PSP/SMU or already issued GPU writeback has drained. |
| [`mes_v11_0_enable`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/mes_v11_0.c#L813-L860) and [`gfx_v11_0_hw_fini`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/gfx_v11_0.c#L4343-L4378) | MES halt/reset is separate from disabling the managed GFX/Compute queues, stopping CP, and disabling GART. The non-VF teardown logs some failures and continues. | A control write or successful top-level teardown return does not certify that all prior DMA/writebacks are visible or finished. Linux's teardown and allocation lifecycle are not build34's initial ownership contract. |
| [`soc21_asic_reset_method`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/soc21.c#L343-L394), [`soc21_need_reset_on_init`](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/amdgpu/soc21.c#L435-L449), and [SMU 13.0.4 Mode 2](https://github.com/torvalds/linux/blob/adc218676eef25575469234709c2d87185ca223a/drivers/gpu/drm/amd/pm/swsmu/smu13/smu_v13_0_4_ppt.c#L1020-L1024) | The default reset selector uses Mode 2 for MP1 13.0.4. Its SMU callback returns the mailbox command result. The separate SOC21 init predicate returns false for APUs. | Neither the recovery selector nor the init predicate establishes that a normal macOS restart reset the APU, that the firmware can safely take this command at startup, or what old writers are covered. |

## Ordering gap in build34

The production `PhxBringup::start()` enables PCI bus mastering and memory
decoding before it maps the BARs and publishes the service. The shell can
therefore guard its own work only; it cannot establish the device state before
those PCI changes. The production `full.sh` calls `bringup5.sh` before
unhalting CP, running GART and starting MES. That script destroys and recreates
the PSP ring and stages firmware. `mesboot gart` writes page tables before
queue adoption.
`mes_start()` then writes MES reset and active controls. `kiq_init_only()` and
`sched_init()` clear fixed ring/writeback storage before `hqd_program()` writes
`ACTIVE=0` and reprograms the queue. `compute_via_mes()` and `gfx_via_mes()`
also clear ring, MQD or writeback storage before issuing `ADD_QUEUE`. Thus a
check at `hqd_program()`, a fresh sentinel after queue setup, or an adoption
check cannot protect the earlier writes to those regions. A successful new
command can coexist with an outstanding old write to a different location.

`mesboot` uses the build34 layout wrappers: a failed transport or wrong reply
size exits before a register value is returned. This still does not identify
which indexed register bank supplied a successful read. `grbm_select()` and
the later reads/writes are separate IOKit calls. The staged raw gate serializes
individual mutators, so other admitted writers can intervene between calls;
the shell reservation covers only the paired `full.sh` entrypoint. Writing
the selector to sample HQDs is itself a device write. Do not add that sequence
to the accepted passive BAR observer or run it on the active desktop.

## Evidence required before reusing storage

1. Identify the current device, service, boot and first writer before *any*
   reused bootstrap storage is changed, including the PSP and GART paths.
   Bind all initial setup writers to the same exclusive scope. Make any
   index/select/read/restore observation an indivisible driver transaction
   with the required device power and mapping lifetime held. Reject an
   unknown owner, failed access or conflicting queue identity.
2. For an owned predecessor, establish the completion boundary for stopping
   new work and draining already issued work on each relevant device writer.
   For an unowned predecessor, require independently verified cold/reset
   semantics or disjoint, independently reserved storage with old mappings
   and global engine state protected. Separating the fence pages alone does
   not prevent interference through GART, queue control, or firmware memory.
   Do not infer either route from a new boot ID or a local process exit.
3. Validate the refusal path offline first: failed or short transport, index
   interference, dequeue timeout, and a delayed old write after an inactive
   sample or after fresh new work. Require that uncertainty prevents touching
   the affected storage, adopting queues or releasing old resources. A stale
   completion after publication must keep the scope quarantined.
4. Establish the mapping/writeback visibility contract separately before
   binding the exact reader. Any later hardware observation needs its own
   admitted scope and independent rollback; the previous mapping-only boot
   cannot establish initial queue state or drain.

No reset, unmap, dequeue, or new register test is proposed for the installed
build34 stack. Continue with exclusive boot-time ownership and a verified
mechanism for the unknown-predecessor case before enabling exact completion.
