# Support status: what this branch can and cannot claim

One table, kept current, for the question "does this work on my machine?". It exists because the honest answer
differs per area, and because `README.md`'s status table describes **upstream's reference machine**, not this
branch: nothing in this fork has been run on any laptop yet.

**No row below is `target-verified`.** The target is a ThinkBook with a Radeon 780M (Phoenix, gfx1103, PCI
`1002:1900`), planned for macOS Tahoe on an external disk. Migration and the actual target OS build remain
unverified; until the phase-1 capture (`docs/analysis.md` §7) has run there, every claim in this repository is host-side.

## Evidence classes

| class | means | is not |
| --- | --- | --- |
| `target-verified` | observed on the target laptop, with a record in `docs/validation/` | — (none yet) |
| `host-verified` | compiled, linked, signed or executed on a non-target host in CI | that anything loads or draws |
| `policy-asserted` | a decision rule is asserted by a C++/Python test that runs on every push | that the rule meets real hardware |
| `not implemented` | the driver does not attempt it | "broken"; it is out of scope, deliberately |
| `unknown` | this repository cannot decide it, and says so instead of guessing | a soft yes |

## The table

| area | what the code does today | evidence class | where the evidence lives | what would move it up |
| --- | --- | --- | --- | --- |
| Device gate | Starts only with `phx780m=1` on Darwin 25 and PCI `1002:1900`; otherwise declines | `policy-asserted` | `tests/test_hardware_policy.cpp`, `src/phxaccel/PhxHardwarePolicy.hpp` | one boot on the target with the boot argument, and one without |
| Firmware loading (PSP, TOC, TMR, nine-file sequence) | Whole-file SHA-256 snapshots, checked extents, seventeen typed IP loads | `host-verified` (synthetic transports) | `tools/test_firmware_sequence.py`, `tools/test_firmware_control.py`, `docs/FIRMWARE-SEQUENCE.md` | a load on the target with the PSP status readback that follows it |
| PSP / TOC lifecycle | Terminal completion checks, TMR readiness, no fabricated success | `host-verified` (fake IOKit) | `tools/test_psp_submission.py`, `docs/PSP-COMPLETION.md` | the same, on hardware |
| GART / GPUVM bootstrap | MC and physical addresses derived, no reference constants | `host-verified` (synthetic registers) | `tools/test_gart_bootstrap.py`, `docs/GART-BOOTSTRAP.md` | a walk on hardware with the readback compared |
| Page tables, VMID binding, retirement | Checked backing, ownership transfer, no synthetic fence retirement | `host-verified` | `tools/test_page_tables.py`, `tools/test_vm_binding.py`, `tools/test_vm_walk_cleanup.py`, `tools/test_bo_retirement.py`, `tools/test_context_retirement.py` | real GPUVM work on the target |
| MES scheduler, queues, compute ring | Relocated layouts, checked completions, exclusive-ownership gaps documented | `host-verified` (synthetic completions) | `tools/test_mes_start.py`, `tools/test_mes_queue.py`, `tools/test_compute_probe.py`, `docs/MES-START.md`, `docs/QUEUE-ADOPTION.md` | a submission the GPU actually retires |
| GFX power (SMU/IMU, RLC readiness) | Acknowledged power request, bounded boot-readiness polls | `host-verified` (synthetic) | `tools/test_firmware_sequence.py --power`, `docs/GFX-POWER.md` | a power-up on the target |
| Shader dispatch (GFX11 probe, native GPUVM probe) | Fixed licensed shader, whole-arena guards, native ABI | `host-verified` (injected GPU writes) | `tools/test_shader_probe.py`, `tools/test_native_shader_probe.py`, `docs/GFX11-SHADER-PROBE.md`, `docs/NATIVE-SHADER-PROBE.md` | one dispatch whose output the GPU wrote |
| Metal plugin, AIR→SPIR-V translator, RADV | Built, linked, signed; SPIR-V and AIR validated; metallib compiled without a device | `host-verified` on `macos-15-intel` | `macos-kexts` CI job, `docs/BUILD.md` | a Metal device created by an app on the target |
| Probes refusing a wrong host | `metal-smoke` and `native-shader-probe` refuse a non-780M host (exit 4) | `host-verified` | `macos-kexts` CI job | — (this one is a refusal, proven where it must work) |
| BO arithmetic and profile provenance | Page-rounding/budget overflow refusal, missing-kernel-view handling; flags label the assumed profile and software budgets | `host-verified` (actual allocation methods with IOKit fakes) | `tools/test_bo_create.py`, `docs/validation/priority-host-20261112.md` | actual IP discovery, allocation/fault execution and pressure testing on the target |
| Optional Metal capability declarations | Live-backend/translator dependencies gate function pointers and dynamic libraries; barycentric and whole-family conformance claims are denied | `host-verified` (96 dependency combinations) | `docs/METAL-CAPABILITIES.md`, `docs/validation/priority-host-20261112.md` | positive shader/feature/limit execution evidence for each promoted declaration on the target |
| Adopted sampler and IOSurface keys (PRs 6-7) | Immutable sampler-slot keys and full-width collision-safe surface keys are in downstream source; locks, weak lifetimes and seed/backing checks are retained | `host-verified` (Foundation/helper and actual registry/monitor methods with CPU doubles) | `docs/UPSTREAM-ADOPTION.md`, `docs/validation/upstream-adoption-20261112.json` | target rendering, screenshots, video and multi-window regression; measured latency before a speedup claim |
| Adopted descriptor masks (PR 8) | Separately bound framebuffer-fetch descriptors are excluded from ordinary-stage masks, with legacy/unknown/tessellation fallbacks | `host-verified` (321 cases in three configurations per host, actual parser/writer with Vulkan doubles) | `docs/UPSTREAM-ADOPTION.md`, `docs/validation/upstream-adoption-20261112.json` | target shader/framebuffer-fetch output and descriptor correctness under real Vulkan/GPU execution |
| Shader-cache correctness | Bounded LRU payload/count; checked version/kind/length/checksum and unique atomic writes for base SPIR-V/index/key memo | `host-verified` (host I/O/Foundation only) | `docs/SHADER-CACHE.md`, `docs/validation/priority-host-20261112.md` | correct translated shader output, hit/miss behavior and measured latency under a target workload |
| Failed upload-prologue refusal | No main QueueSubmit after its prologue End fails; unsubmitted cleanup is distinct from uncertain-submit retention | `host-verified` (33 actual-body fake-API cases) | `docs/SUBMIT-FAILURE-CONTRACT.md`, `docs/validation/priority-host-20261112.md` | target upload/fill correctness and fault behavior; no reset/sleep implementation is implied |
| Hardware gamma and CLUT | Both gamma callbacks and CLUT explicitly return unsupported; no LUT is programmed | `not implemented` | `docs/DISPLAY-CAPABILITIES.md`, `docs/validation/priority-host-20261112.md` | an AMD LUT programming implementation followed by target color verification |
| Framebuffer takeover | Takes over the mode the firmware already lit; no mode set, no display-engine programming | `policy-asserted` | `docs/DISPLAY-PATH.md`, `docs/analysis.md` §1 | the panel coming up on the target and the `phx-fb-phys` publish in the log |
| Native 2x HiDPI candidate | Opt-in `phxfbhires=1` marks the existing physical mode HiRes-eligible; an offline override offers half-sized logical coordinates with unchanged backing pixels. No resampling or new hardware mode | `host-verified` (compile/sign, CPU callback and probe only) | `docs/HIDPI.md`, `docs/validation/hidpi-native-20261112.md`, `tools/test_hidpi.py` | the actual Tahoe build, current CoreGraphics logical/backing dimensions at exactly 1:2 matching the GOP raster, and a stable visible desktop on the target |
| Read-only detailed panel timing (PR 9) | Stable bounded OTG0 snapshots can describe the existing boot raster; estimated pixel clock, unknown min/max bounds and legacy fallback; no display register writes or new modes | `host-verified` (43 decoder cases and actual timing callback with IOKit doubles, native SDK compilation) | `docs/DISPLAY-CAPABILITIES.md`, `docs/UPSTREAM-ADOPTION.md`, `docs/validation/upstream-adoption-20261112.json` | target mode information and stable visible desktop with independently checked physical timing on the recorded OS build |
| Copy path and scan-out alias | Every frame is copied; BAR view or verified carve-out view, the alias accepted only when every sample matches the BAR and one is non-zero, and a present before publication spends no verification budget. Which view is faster is a fixed preference here (`debug.phxfb_alias`), not a measurement | `policy-asserted` (patch 0028) | `tests/test_hardware_policy.cpp` (budget and acceptance), `tests/test_framebuffer_path.py` (the driver calls them), `docs/DISPLAY-PATH.md` | a capture showing which destination was live, the `alias: ... samples match the BAR` log line, and the B4 A/B. A sibling port now measures both views at startup instead of keying on the chip (`docs/RADEARC-REFERENCE.md` §6) |
| Copy row path and colour narrowing | 64-byte SSE / 8-byte pair / 4-byte paths chosen from alignment, stride and `debug.nvaccel_iop_sse`; ARGB2101010 → XRGB8888 while copying; `debug.nvaccel_iop_damage=1` stores only the 64-byte groups a frame changed (default off, shadow rules asserted) | `policy-asserted` | `tests/test_copy_path.cpp`, `src/phxaccel/PhxCopyPath.hpp` | `iop_damage_bytes` and `avg_copy_us` from a B5 A/B (the capture records both), and a screenshot that proves the colours on the panel |
| BO handles per client | 4096 slots per client, 4095 usable (`PHXN_MAX_BOS`); a full table refuses the BO with `kIOReturnNoResources` and logs once; `debug.phxbos_handles_high` records the highest index handed out and `debug.phxbos_handles_full` counts the refusals | `host-verified` (counters, no ceiling test) | `tests/test_counter_contract.py` (the names are declared, captured and documented), `docs/analysis.md` §4 | a capture whose `bos_handles_high` is well below 4095 — or a non-zero `bos_handles_full`, which would prove the cliff is real on this machine. Raising the limit needs the user-space table raised at the same time, so it stays untouched until then |
| BO memory in the kernel map | Driver-created BOs use `IOBufferMemoryDescriptor` in `kernel_task` with a permanent kernel view; host imports pin existing descriptors. Arithmetic checks do not relieve kernel-VA pressure. A sibling port's reported exhaustion/client-map change is not target evidence | `unknown` | `docs/BRINGUP-AUDIT.md` (second pass), `docs/RADEARC-REFERENCE.md` §6, `docs/IMPROVEMENT-PLAN.md` | see "Rows no capture can move" — no display-path counter can show it |
| Present pacing | Complete on the next VBL tick, force-complete past two refreshes, four held frames then copy | `policy-asserted` | `tests/test_present_pacing.cpp`, `src/phxaccel/PhxPresentPacing.hpp` | `debug.nvaccel_iop_gap*` and `_vsync_*` from the target |
| Frame rate, judder, "is it smooth" | Instrumented, not measured: the counters and the read-only capture exist | `unknown` | `tools/phx_baseline.sh`, `tools/phx_baseline_report.py`, `docs/analysis.md` | one phase-1 capture plus the H1–H4 verdict |
| Panel timing and modes other than the firmware mode | Not attempted: only the firmware-lit mode, read from the OTG | `not implemented` | `docs/DISPLAY-PATH.md` | a separate mode-setting project |
| Backlight | Not attempted | `not implemented` | `docs/DOWNSTREAM-ROADMAP.md` | — |
| Display sleep / wake repaint | Not verified; the upstream comment describes a fragmenting-pool failure | `unknown` | `docs/analysis.md` §3, patch 0028 rationale | a capture window that spans a sleep/wake: ticks continuing while `frames_on_panel` stops says the copy path died on wake, and both moving says it survived. Whether the panel actually lit stays a human look |
| External displays (HDMI, USB-C) | Not attempted | `not implemented` | `docs/DOWNSTREAM-ROADMAP.md` | — |
| Hardware video decode/encode | Not attempted | `not implemented` | `docs/DOWNSTREAM-ROADMAP.md` | — |
| Install plan (what to add to an EFI, and how to revert it) | `tools/phx_install_plan.py` reads an existing `config.plist` and writes numbered operator steps plus the rollback; no apply mode, and it refuses system locations, foreign kexts and unmatched digests | `host-verified` (synthetic layouts) | `tests/test_install_plan.py`, `docs/INSTALL-PLAN.md` | one reviewed install on the target, then the driver attaching |
| Installer, uninstaller, rollback package | None shipped and none planned: `tools/phx_boot_gate.sh` runs stages but ships none, and the plan tool writes steps instead of performing them. The security changes upstream's install needs stay the owner's decision, not the repository's action | `not implemented` | `docs/BOOT-GATE.md`, `docs/INSTALL-PLAN.md` | an installer that stays step-revertible and touches no system location |
| Other 780M / 760M machines (Hawk Point, other panels) | Nothing is claimed for them | `unknown` | `tools/target_inventory.py` (the read-only inventory a report would carry) | an inventory file from one of those machines; nothing about them can be inferred from ours |

## What one capture would move, field by field

Most rows above say "a capture" without saying which number. This is that mapping, and it is the reason each
instrumented row names a field that `tools/phx_baseline.sh` actually writes: a row whose field the capture does
not record can never move, and it would read as "waiting for hardware" instead of "cannot be answered".

| capture field | row it moves | what value would move it |
| --- | --- | --- |
| `copy_share_of_refresh_pct`, `presents_per_s`, `vbl_hz` | Frame rate, judder | H1 supported or refuted by `tools/phx_baseline_report.py` — either way the row stops being `unknown` |
| `vbl_late_avg_us`, `vbl_late_max_us` | Present pacing | lateness above the §9 line makes B2 the next step, below it retires the tick question |
| `iop_gap1`–`iop_gap4`, `iop_vsync_waits`, `iop_vsync_late` | Present pacing | an even cadence refutes H3; two-or-more-refresh gaps support it |
| `iop_damage_bytes`, `iop_damage_full_frames` | Copy row path and colour narrowing | a B5 A/B where stored bytes drop and `avg_copy_us` follows — or does not |
| `bos_handles_high`, `bos_handles_full` | BO handles per client | a high-water mark far from 4095 is headroom; a non-zero `bos_handles_full` is the ceiling being hit for real |
| the `alias:` lines in the kernel log | Copy path and scan-out alias | one `samples match the BAR` line proves the carve-out view was verified at least once |
| `phx-fb-phys` / `phx-build` in `ioreg.txt` | Framebuffer takeover | the driver publishing what it took over, on the target |
| `frames_on_panel`, `vbl_ticks` across a sleep/wake | Display sleep / wake repaint | ticks continuing while copies stop is the wake failure; both moving says the copy path survived. Whether the panel lit is still a human look |
| `knobs` | every row | they say which path the numbers describe; a capture whose knobs are missing is not comparable |

A field in that table is a promise the tool keeps: `tests/test_phase1_baseline_shell.py` asserts the JSON carries
it, and `tests/test_baseline_report.py` asserts the verdict tool reports it.

## Rows no capture can move, and why

`unknown` and `not implemented` look alike in the table and are not alike at all. The rows below are not waiting
for the phase-1 session; listing them here keeps them from reading as gaps that one more capture would close.

| row | why a capture cannot move it | what would |
| --- | --- | --- |
| Panel timing and modes other than the firmware mode | `not implemented`: the driver never programs the display engine, so the counters report the firmware's mode whether or not anything else could be done | a mode-setting project of its own (`docs/DISPLAY-PATH.md`) |
| Backlight | `not implemented`: no backlight register is written, and a capture cannot tell "backlight at zero" from "backlight never touched" | backlight control code first |
| Hardware gamma and CLUT | `not implemented`: callback refusal is tested but there is no LUT programming path for a capture to exercise | AMD LUT programming code and a target color/calibration check |
| External displays (HDMI, USB-C) | `not implemented`: there is no encoder or hotplug path to observe | an external-display project; plugging a screen in would exercise code that does not exist |
| Hardware video decode/encode | `not implemented`, and out of scope by the work order | separate engine work |
| Installer, uninstaller, rollback package | `not implemented`: `tools/phx_install_plan.py` writes steps and `tools/phx_boot_gate.sh` runs stages; neither ships an installer, so there is no installer whose behaviour a capture could describe | a reviewed install on the target, done by a human, and a record that says so |
| Other 780M / 760M machines | `unknown` for *those* machines: our machine's numbers say nothing about them, and no capture of ours can | `tools/target_inventory.py` run on one of them — one file from that machine, nothing from here |
| BO memory in the kernel map | it is a count of kernel mappings held by live BOs, not a display-path number: no field in the capture moves it, and the failure it predicts (a `KERN_NO_SPACE` abort) shows up as the compositor dying, not as a lower present rate | a multi-hour session with a real workload and no abort, or the client-map allocation a sibling port already ships (`docs/BRINGUP-AUDIT.md`, second pass) |

## How to keep this table honest

- A row moves up only with evidence of the class above it: a CI run, a target capture, or a recorded refusal.
  Nothing here moves because a document says so — `docs/analysis.md` and the code are authoritative.
- Every `unknown` row appears in one of the two accounting sections above, and a `—` in the move-up column is only
  allowed for a row explained in "Rows no capture can move". `tests/test_support_status.py` enforces both, so the
  table cannot grow a row that reads as "waiting for hardware" when it is waiting for a project, or for another
  machine.
- When a row changes, change it in the same commit that produces the evidence, and name the record (a
  `docs/validation/` file or a CI run) next to it.
- `README.md`'s status table stays as upstream wrote it, because it is upstream's measurement; this file is
  the one that answers for this branch.

Corresponds to `downstream/780m-tahoe` as of the commit that last changed this file; the rows above name the
test, CI job or record behind each one, and those are what to check, not this date.
