# Support status: what this branch can and cannot claim

One table, kept current, for the question "does this work on my machine?". It exists because the honest answer
differs per area, and because `README.md`'s status table describes **upstream's reference machine**, not this
branch: nothing in this fork has been run on any laptop yet.

**No row below is `target-verified`.** The target is a ThinkBook with a Radeon 780M (Phoenix, gfx1103, PCI
`1002:1900`) on an external-disk macOS Tahoe install; until the phase-1 capture (`docs/analysis.md` §7) has run
there, every claim in this repository is host-side.

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
| Page tables, VMID binding, retirement | Checked backing, ownership transfer, no synthetic fence retirement | `host-verified` | `tools/test_page_tables.py`, `test_vm_binding.py`, `test_vm_walk_cleanup.py`, `test_bo_retirement.py`, `test_context_retirement.py` | real GPUVM work on the target |
| MES scheduler, queues, compute ring | Relocated layouts, checked completions, exclusive-ownership gaps documented | `host-verified` (synthetic completions) | `tools/test_mes_start.py`, `test_mes_queue.py`, `test_compute_probe.py`, `docs/MES-START.md`, `docs/QUEUE-ADOPTION.md` | a submission the GPU actually retires |
| GFX power (SMU/IMU, RLC readiness) | Acknowledged power request, bounded boot-readiness polls | `host-verified` (synthetic) | `tools/test_firmware_sequence.py --power`, `docs/GFX-POWER.md` | a power-up on the target |
| Shader dispatch (GFX11 probe, native GPUVM probe) | Fixed licensed shader, whole-arena guards, native ABI | `host-verified` (injected GPU writes) | `tools/test_shader_probe.py`, `test_native_shader_probe.py`, `docs/GFX11-SHADER-PROBE.md`, `docs/NATIVE-SHADER-PROBE.md` | one dispatch whose output the GPU wrote |
| Metal plugin, AIR→SPIR-V translator, RADV | Built, linked, signed; SPIR-V and AIR validated; metallib compiled without a device | `host-verified` on `macos-15-intel` | `macos-kexts` CI job, `docs/BUILD.md` | a Metal device created by an app on the target |
| Probes refusing a wrong host | `metal-smoke` and `native-shader-probe` refuse a non-780M host (exit 4) | `host-verified` | `macos-kexts` CI job | — (this one is a refusal, proven where it must work) |
| Framebuffer takeover | Takes over the mode the firmware already lit; no mode set, no display-engine programming | `policy-asserted` | `docs/DISPLAY-PATH.md`, `docs/analysis.md` §1 | the panel coming up on the target and the `phx-fb-phys` publish in the log |
| Copy path and scan-out alias | Every frame is copied; BAR view or verified carve-out view, alias verified by 4096 sample comparisons | `policy-asserted` (patch 0028) | `tests/test_hardware_policy.cpp`, `docs/DISPLAY-PATH.md` | a capture showing which destination was live and its cost |
| Copy row path and colour narrowing | 64-byte SSE / 8-byte pair / 4-byte paths chosen from alignment, stride and `debug.nvaccel_iop_sse`; ARGB2101010 → XRGB8888 while copying | `policy-asserted` | `tests/test_copy_path.cpp`, `src/phxaccel/PhxCopyPath.hpp` | a capture's `copy_us`, and a screenshot that proves the colours on the panel |
| Present pacing | Complete on the next VBL tick, force-complete past two refreshes, four held frames then copy | `policy-asserted` | `tests/test_present_pacing.cpp`, `src/phxaccel/PhxPresentPacing.hpp` | `debug.nvaccel_iop_gap*` and `_vsync_*` from the target |
| Frame rate, judder, "is it smooth" | Instrumented, not measured: the counters and the read-only capture exist | `unknown` | `tools/phx_baseline.sh`, `tools/phx_baseline_report.py`, `docs/analysis.md` | one phase-1 capture plus the H1–H4 verdict |
| Panel timing and modes other than the firmware mode | Not attempted: only the firmware-lit mode, read from the OTG | `not implemented` | `docs/DISPLAY-PATH.md` | a separate mode-setting project |
| Backlight | Not attempted | `not implemented` | `docs/DOWNSTREAM-ROADMAP.md` | — |
| Display sleep / wake repaint | Not verified; the upstream comment describes a fragmenting-pool failure | `unknown` | `docs/analysis.md` §3, patch 0028 rationale | a wake on the target with the panel repainting |
| External displays (HDMI, USB-C) | Not attempted | `not implemented` | `docs/DOWNSTREAM-ROADMAP.md` | — |
| Hardware video decode/encode | Not attempted | `not implemented` | `docs/DOWNSTREAM-ROADMAP.md` | — |
| Install plan (what to add to an EFI, and how to revert it) | `tools/phx_install_plan.py` reads an existing `config.plist` and writes numbered operator steps plus the rollback; no apply mode, and it refuses system locations, foreign kexts and unmatched digests | `host-verified` (synthetic layouts) | `tests/test_install_plan.py`, `docs/INSTALL-PLAN.md` | one reviewed install on the target, then the driver attaching |
| Installer, uninstaller, rollback package | None shipped and none planned: `tools/phx_boot_gate.sh` runs stages but ships none, and the plan tool writes steps instead of performing them. The security changes upstream's install needs stay the owner's decision, not the repository's action | `not implemented` | `docs/BOOT-GATE.md`, `docs/INSTALL-PLAN.md` | an installer that stays step-revertible and touches no system location |
| Other 780M / 760M machines (Hawk Point, other panels) | Nothing is claimed for them | `unknown` | — | a report from one of those machines |

## How to keep this table honest

- A row moves up only with evidence of the class above it: a CI run, a target capture, or a recorded refusal.
  Nothing here moves because a document says so — `docs/analysis.md` and the code are authoritative.
- When a row changes, change it in the same commit that produces the evidence, and name the record (a
  `docs/validation/` file or a CI run) next to it.
- `README.md`'s status table stays as upstream wrote it, because it is upstream's measurement; this file is
  the one that answers for this branch.

Corresponds to `downstream/780m-tahoe` as of the commit that last changed this file; the rows above name the
test, CI job or record behind each one, and those are what to check, not this date.
