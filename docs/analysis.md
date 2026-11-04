# Display path and shader-cache analysis (phase-1 input)

What this file is: a reading of the code that decides how a composited frame reaches the 780M's panel and
what the Metal plugin caches, written to decide which optimisation — if any — is worth implementing.
Every claim names the code that makes it; **documents and their version numbers are not evidence**, and
none of this has been measured on the target laptop yet.

Nothing here was measured. The counters it names already exist in the code, and
`tools/phx_baseline.sh` reads them; until that has run on the target, phase 1 (§7) has no data and §6
explains why no optimisation is implemented.

## 1. How a frame reaches the panel

```
Metal app ─► NVMTLDriver.bundle (src/nmplugin) ─► Mesa RADV (Mesa pin in upstream.lock.json)
          ─► PhxBringup (GPU work, src/phxbringup) ─► frame lands in an IOSurface / our VRAM resource
WindowServer ─► NVAccel display pipe (src/phxaccel/accel/nvrm-accel.cpp)
          ─► CPU copy into the boot console's scan-out  ─► panel reads that buffer
```

PhxAMDFB does not program the display engine: it takes over the mode the firmware already lit, and the
accelerator copies each finished frame into a CPU mapping of the console's scan-out. See the file header at
`src/phxaccel/accel/phxfb.cpp:1-6` and `src/phxaccel/accel/phxfb.cpp:58-81` for the class state.

### 1.1 The copy is mandatory on this hardware

`nvAccelIopFlip()` (`src/phxaccel/accel/nvrm-accel.cpp:2121-2181`) is the zero-copy path — scan the
surface out of its own VRAM, no copy. It refuses this framebuffer outright:

```c
// zero-copy scan-out is an NVIDIA display-engine flip; another vendor's panel (NMIntelFB) always takes the copy
if (!fb->metaCast("NVRMNVDAFramebuffer")) return false;      // nvrm-accel.cpp:2124-2125
```

So on the 780M **every presented frame costs a CPU copy** (`performTransaction`,
`nvrm-accel.cpp:1124-1280`). Any smoothness work here is work on the copy path; "turn on zero-copy" is not
available until the display engine is programmed, which is a different project, not an optimisation.

### 1.2 Where the copy lands, and why that dominates

The destination is chosen in `PhxAMDFB::callPlatformFunction` for `NVRM_VRAM_FN_SCANOUT`
(`phxfb.cpp:434-451`), using `aliasMap()` (`phxfb.cpp:386-433`):

| destination | mapping | cost recorded in the code |
| --- | --- | --- |
| BAR view of the scan-out, `fSurfMap` | write-combined (`kIOMapWriteCombineCache`) | "a 2560x1600 frame took ~110 ms to copy (~7 fps, the whole desktop lagged)" (`phxfb.cpp:63-65`) |
| system-RAM view, `fAliasMap` | carve-out addressed through RAM; comes out **write-back** whatever was asked | comment at `phxfb.cpp:62-66`, hence non-temporal stores in the copy |

`debug.phxfb_alias` selects between them (`phxfb.cpp:32-35`): 1 = through the carve-out, 0 = through the BAR.
The alias is only used after it has been verified against the BAR — 4096 sampled words must match and be
non-zero (`phxfb.cpp:414-429`) — and only once PhxBringup publishes `phx-fb-phys`
(`phxfb.cpp:390-413`). Before that, presents are counted as waits (`kAliasWaitLimit` 3600), not failures;
after three real mismatches the session stays on the BAR copy for its whole life
(`phxfb.cpp:67-70`, `phxfb.cpp:406-414`).

Consequence for phase 1: **the first baseline datum is which of the two paths is live**, because the same
"optimisation" is a 15× difference in frame cost depending on it.

### 1.3 The copy itself

`performTransaction` picks the source, then copies one row at a time (`nvIopCopyFull()`, `nvrm-accel.cpp:1167-1204`), unless the damage-only path stores the changed 64-byte groups instead (`nvIopCopyDamage()`, `nvrm-accel.cpp:1053-1165`):

- source: our VRAM resource, else the IOSurface's system memory
  (after `nvAccelSurfCopyReady()`, `nvrm-accel.cpp:2340`, and `nvSurfWaitReady`).
- narrowed formats: WindowServer moves to 10-bit `l10r` (ARGB2101010) once colour management is up and the
  panel is 8-bit XRGB, so those frames lose two bits per channel while copied
  (`nvIopCopyFull()`, `nvrm-accel.cpp:1170-1174`, `1193`, `1195`).
- inner loop: 8-byte `movnti` pairs by default; a 64-byte SSE4.1 row (movntdqa/movntdq) only when
  `debug.nvaccel_iop_sse=1` (row selection `nvIopCopyFull()`, `nvrm-accel.cpp:1171-1172`; row routine `nvIopRowSSE()`, `nvrm-accel.cpp:1118-1161`). Measured in the code's
  own comments: 1.0 ms per frame with SSE against 2.1 ms without (`tools/phxctl/phxboot.sh:63-64`), and
  plain loads on a write-combined surface read at ~0.5 GB/s, 13-30 ms per frame
  (`nvIopRowSSE()`, `nvrm-accel.cpp:1118-1120`).
- the SSE routine saves ten XMM registers around every row because x86 XNU switches the FPU lazily and the
  preempted thread may be a user thread whose registers the kernel does not save
  (`nvIopRowSSE()` prologue, `nvrm-accel.cpp:1121-1131`) — per-row overhead paid per row, not per frame.
- `sfence` before the transaction is reported complete (`nvIopCopyFull()`, `nvrm-accel.cpp:1203`): the frame must be in DRAM
  before the panel may read it.

### 1.4 Present pacing

A copied frame is reported complete on the **next** VBL tick, as a flip would latch
(`nvrm-accel.cpp:1214-1236`, `isTransactionComplete`). The reason is
recorded in the code: completing immediately let WindowServer present twice inside one refresh and then
skip the next — "frames 3-4 ms apart followed by 12-16 ms gaps, 97 presents a second on a 120 Hz panel"
(`nvrm-accel.cpp:1214-1216`). `debug.nvaccel_iop_vsync` defaults to 0 and `tools/phxctl/phxboot.sh:67`
turns it on for the armed panel; past two refreshes a pending transaction completes anyway
(`phx780m::presentCompletion` in `src/phxaccel/PhxPresentPacing.hpp`, asserted by
`tests/test_present_pacing.cpp`), so a broken VBL cannot freeze the desktop.

There is also a per-head hold: at most four frames in a row are kept off the panel when the surface's
newest pixels are still only in VRAM (`nvAccelSurfCopyReady()`, `nvrm-accel.cpp:2340-2370`, limit in
`phx780m::nextCopyHold`), so a surface that never syncs is copied stale rather than freezing the display.

## 2. There is no vblank interrupt

`phxfb.cpp:37-53` and `vblFire` (`phxfb.cpp:218-242`) are explicit: XNU's timer coalescing would move a
120 Hz deadline by up to 1 ms, and thread_call's never-moved urgency is not exported to kexts, so the tick
is armed 1.5 ms early, re-armed for its deadline with an eighth of the previous slop, until less than 50 µs
remain (`debug.phxfb_vbl_staged`, default 1). Lateness is measured per tick and accumulated:
`debug.phxfb_vbl_n`, `debug.phxfb_vbl_late_us_sum`, `debug.phxfb_vbl_late_us_max`
(`phxfb.cpp:44-51`). Up to four VBL handlers are fanned out per tick (`phxfb.cpp:311-330`), including the
one IOAccelDisplayPipe registers, and `gPhxVblSeq` counts ticks before the handlers run because the display
pipe completes on the next one (`phxfb.cpp:46`).

So the VBL a WindowServer-paced display syncs to is a **software timer standing in for an interrupt**.
Jitter and phase here are prime suspects for judder — and the counters to test that already exist.

## 3. Cache keys, shader cache, IOSurface

The plugin is NullMoth's code with AMD changes (`THIRD_PARTY_NOTICES.md`), so its caches are those of the
NVIDIA driver; on this hardware the GPU behind them is RADV.

- **Address-shader cache** (`src/nmplugin/nvmtl_vk.c:3378-3397`): key = the 4-byte `flags` word followed by
  the **entire shader bytes**; a per-process `NSMutableDictionary` guarded by one mutex. When it reaches
  4096 entries it is replaced wholesale (`if (!cache || cache.count >= 4096) cache = [NSMutableDictionary new]`),
  so a full cache loses every entry at once rather than evicting a victim. A key that includes the whole
  blob is correct but makes the dictionary hash the shader on every lookup.
- **Mesa disk cache** (`nvmtl_vk.c:680-689`): if `MESA_SHADER_CACHE_DIR`/`XDG_CACHE_HOME` are unset it uses
  the Darwin user cache dir, and says so in the log — "NAK recompiles every start" when there is no writable
  directory. A missing cache directory is a startup-time problem, not a per-frame one.
- **Other caches**: samplers (`nvmtl_vk.c:2418`), descriptor sets (`2803-2848`, `5555-5561`), image size
  queries (`7689-7730`, escape hatch `NVMTL_NO_SIZEQUERY_CACHE`), and the SSBO-table refusal that can be
  re-enabled with `NVMTL_TABLE_SSBO=1` (`3398-3405`).
- **IOSurface / surface lifetime** (`src/phxaccel/accel/nvrm-accel.cpp`): the flip path caches the
  IOSurface → NVResource mapping (`2121-2144`), `NVAccelSurfaceWait` tells the plugin that `pageoff` waits
  for WindowServer's GPU writes (`nvrm-accel.cpp:671-675`), `nvAccelSurfScanoutSync`/`CopyReady` move the
  newest pixels to system memory before a copy (`2216-2270`), and a surface keeps its VRAM across the
  family's free/alloc (`debug.nvaccel_vm_sticky`, counters `nvaccel_vm_parked`/`_unparked`,
  `nvrm-accel.cpp:1326-1329`).

None of these decide smoothness by themselves; they decide whether a frame can be copied at all without a
stall. The per-frame cost they produce is measured only through the counters in §4.

## 4. The counters that already exist (nothing new is needed to measure phase 1)

Every name below is written in full, because `tools/phx_counter_contract.py` reads this table and fails CI if
the capture script reads a `debug.*` OID this file does not name (or names one the kernel does not declare).

| sysctl | meaning | where |
| --- | --- | --- |
| `debug.phxfb_alias` (rw) | 1 = copy through the carve-out, 0 = through the BAR | `phxfb.cpp:32-35` |
| `debug.phxfb_vbl_staged` (rw) | 1 = staged VBL arming, 0 = one plain deadline | `phxfb.cpp:47-48` |
| `debug.phxfb_vbl_n` | VBL ticks fired | `phxfb.cpp:49` |
| `debug.phxfb_vbl_late_us_sum`, `debug.phxfb_vbl_late_us_max` | tick lateness summed / worst (both rw: writing 0 restarts) | `phxfb.cpp:50-51` |
| `debug.nvaccel_iop` (rw) | 1 = publish display-pipe capabilities and run transactions | `nvrm-accel.cpp:1305-1307` |
| `debug.nvaccel_iop_sse` (rw) | 1 = 64-byte SSE row copy, 0 = 8-byte loads | `nvrm-accel.cpp:1445` |
| `debug.nvaccel_iop_damage` (rw) | 1 = store only the 64-byte groups a frame changed (a shadow of the scan-out is kept per head), 0 = copy every pixel (default) | `nvrm-accel.cpp:1446` |
| `debug.nvaccel_iop_full` (rw) | write 1 to force exactly one full copy while damage-only is on | `nvrm-accel.cpp:1448` |
| `debug.nvaccel_iop_damage_bytes`, `debug.nvaccel_iop_damage_sum` | bytes the last / all damage-only copies stored | `nvrm-accel.cpp:1450-1451` |
| `debug.nvaccel_iop_damage_full`, `debug.nvaccel_iop_damage_busy` | frames the shadow could not help / copies that found it busy | `nvrm-accel.cpp:1452-1453` |
| `debug.nvaccel_iop_vsync` (rw) | 1 = complete a copied frame on the next tick | `nvrm-accel.cpp:1463` |
| `debug.nvaccel_iop_ok`, `debug.nvaccel_iop_ok_h0` … `debug.nvaccel_iop_ok_h4` | frames copied to a panel, per head | `nvrm-accel.cpp:1424-1429` |
| `debug.nvaccel_iop_src_res`, `debug.nvaccel_iop_src_surf` | frames sourced from our VRAM / from the IOSurface | `nvrm-accel.cpp:1439-1440` |
| `debug.nvaccel_iop_copy_skip`, `debug.nvaccel_iop_blank` | frames held back / copied frames that were one colour | `nvrm-accel.cpp:1443`, `1441` |
| `debug.nvaccel_iop_fail` | copy transactions that failed | `nvrm-accel.cpp:1437` |
| `debug.nvaccel_iop_copy_us`, `debug.nvaccel_iop_copy_us_max`, `debug.nvaccel_iop_copy_us_sum` | cost of the last / slowest / all copied frames | `nvrm-accel.cpp:1455-1457` |
| `debug.nvaccel_iop_gap1`, `debug.nvaccel_iop_gap2`, `debug.nvaccel_iop_gap3`, `debug.nvaccel_iop_gap4` | copied frames about one, two, three and four-or-more refreshes after the previous one | `nvrm-accel.cpp:1458-1461`, counted at `1331` |
| `debug.nvaccel_iop_vsync_waits`, `debug.nvaccel_iop_vsync_late` | completion checks answered "not yet" / frames completed past two refreshes without a tick | `nvrm-accel.cpp:1464-1465` |
| `debug.nvaccel_vm_parked`, `debug.nvaccel_vm_unparked` | surfaces that kept their VRAM across a dealloc/alloc | `nvrm-accel.cpp:1416-1417` |
| `debug.nvaccel_iop_bench`, `debug.nvaccel_iop_read_us` | one timed read-only pass over the next source | `nvrm-accel.cpp:1444`, `1454` |
| `debug.phxbos_flush` (rw) | BO cache maintenance per submit/wait: 0 none, 1 clflushopt, 2 clflush | `src/phxbringup/PhxBringup.cpp:39-44` |
| `debug.phxbos_handles_high`, `debug.phxbos_handles_full` | highest BO handle index any client got, and BO creates refused because the per-client table was full | `src/phxbringup/PhxBringup.cpp:45-54` |

The handle counters exist because a sibling port of this base hit the per-client limit (`PHXN_MAX_BOS`, 4095
usable handles) and every texture allocation started failing before WindowServer crashed — a failure that
looks like anything but "out of handles" from user space (`docs/RADEARC-REFERENCE.md` §2). They say whether a
capture is near the cliff without changing the limit, which needs the user-space table raised at the same time.

The gap counters are what make H3 decidable: without them a capture can show that frames reach the panel
slowly, but not whether they arrive evenly. They were readable in the code from the start and
`tools/phx_baseline.sh` now records them, so one capture decides H1 through H4 together.

`debug.phxbos_flush` matters to compositing too: with `clflush`, "WindowServer spent ~73% of its CPU here
and composited ~13 fps; with none, 41 fps" (`PhxBringup.cpp:35-38`) — the default is 0, and
`tools/phxctl/phxboot.sh:51-53` sets it explicitly.

## 5. Hypotheses

The work order refers to H1–H4 but neither the issue nor the repository defines them. These are the four
that the code above makes testable; **they are proposals for the owner to confirm, not the H1–H4 that were
asked for**.

| id | hypothesis | decides it | code it would touch | if false |
| --- | --- | --- | --- | --- |
| H1 | The copy cost, not the panel rate, limits present rate: one copied frame is a large share of a refresh and frames reach the panel slower than the VBL ticks | `copy_share_of_refresh_pct` and `presents_per_s` vs `vbl_hz` from `phx_baseline.sh` | copy loop `nvrm-accel.cpp:1225-1254`; destination `phxfb.cpp:434-451` | no copy optimisation: cost is not the limiter |
| H2 | The software VBL's jitter (not the copy) is the judder source, so presents land on the wrong side of a refresh | `vbl_late_avg_us`/`vbl_late_max_us`, and the A/B with `debug.phxfb_vbl_staged=0` | `vblFire`, `phxfb.cpp:218-242` | leave the tick alone |
| H3 | Present pacing is wrong rather than slow: duplicate presents inside one refresh followed by a gap | gap buckets `gCntIopGap[4]` (`nvrm-accel.cpp:1209-1218`) plus `copy_skip`/`blank`, A/B on `nvaccel_iop_vsync` | `isTransactionComplete`, `1096-1117` | pacing is not the problem |
| H4 | Surface readiness stalls are showing up as repeated frames | `debug.nvaccel_iop_copy_skip`, `nvaccel_iop_blank`, `nvaccel_vm_parked`/`_unparked` | `nvAccelSurfCopyReady`, `2240-2270`; sticky VRAM `1326-1329` | no readiness work |

Each hypothesis has an A/B switch that already exists, so confirming one costs a boot argument, not a
commit. If none of them holds, the honest next step is to measure application-side cost (CPU time in
`phxbos_flush`, plugin dispatch, RADV) before touching the display path.

## 6. Why nothing is implemented in this change

- The work order gates implementation on confirmed hypotheses, and confirming them needs the phase-1
  baseline. No baseline exists: there is no recorded run of this driver on the target laptop, and the
  numbers quoted above are comments written by the upstream author in October 2026, not measurements this
  project made.
- H1–H4 were not defined anywhere the repository or the issue can see, so "which hypotheses hold" cannot
  even be answered on paper. §5 proposes a set to confirm.
- Inventing a before/after table without a measurement would be exactly the fabricated evidence this
  project forbids.

What this change *does* add: this analysis, `tools/phx_baseline.sh` — the read-only capture that makes
phase 1 a command instead of a discussion — and `tools/phx_baseline_report.py`, which computes the verdict
below from that capture (§7, §9).

## 7. Phase 1, exactly

```sh
# on the target laptop, from a normal session, with the accelerated panel up
sh tools/phx_baseline.sh --out /Users/Shared/phx-baseline-$(date +%Y%m%d-%H%M) --window 60 --samples 3
sh tools/phx_baseline.sh --out /Users/Shared/phx-baseline-snapshot   # counters once, no window

# anywhere, on the capture (no hardware needed to compute the verdict)
python3 tools/phx_baseline_report.py baseline=/Users/Shared/phx-baseline-20261103-1010 --out build/verdict
python3 tools/phx_baseline_report.py baseline=BASE b1-sse-off=B1 b2-plain-tick=B2 b3-immediate=B3 b4-bar=B4
```

The capture writes `vbl_hz`, `presents_per_s`, `avg_copy_us`, `copy_share_of_refresh_pct`, `copy_skip`,
`blank_frames`, `iop_fail`, `vbl_late_avg_us`/`_max`, the present cadence (`iop_gap1`–`iop_gap4`,
`iop_vsync_waits`, `iop_vsync_late`) and the knob values that say which path was measured; `summary.txt`
prints the same numbers by hand. `tools/phx_baseline_report.py` applies §9 to them and prints which
hypothesis the capture supports, which it refutes, and which it cannot decide — a capture without the
cadence counters leaves H3 undecidable instead of guessed. Also record the `alias:` lines from the kernel
log: they say whether the carve-out view was ever verified. Then repeat the 60 s window three times with
the A/B switches, one at a time, changing nothing else:

| run | change | question |
| --- | --- | --- |
| B1 | `debug.nvaccel_iop_sse=0` (versus the arming default of 1) | how much of the copy cost is the row copy |
| B2 | `debug.phxfb_vbl_staged=0` | is the staged tick worth it, and how late is a plain deadline |
| B3 | `debug.nvaccel_iop_vsync=0` | does the next-tick completion actually change the cadence |
| B4 | `debug.phxfb_alias=0` | the BAR copy baseline (expected to be much worse; it is the control, not a candidate) |
| B5 | `debug.nvaccel_iop_damage=1` | is the cost the number of stored bytes or their price: `damage_sum` says how much was stored, `copy_us` whether it got faster, `damage_full` how often the shadow could not help |

Each A/B capture goes in as `label=PATH` after the baseline capture, and the report prints the change per
metric with a noise caveat: one window per side is a single sample.

Acceptance for phase 1 is a filled table, not a verdict: it decides H1–H4 and nothing else.

## 8. Switch and rollback rules for whatever comes next

- Every optimisation is its own commit and its own boot argument (or its own value of an existing sysctl
  where that is already the pattern), defaulting to today's behaviour. With the switch absent, the code
  path and its timing must be the ones measured in phase 1.
- Rollback of a commit: `git revert <sha>`, rebuild the two kexts, reinstall, boot. No NVRAM, BIOS or
  firmware state is involved, so nothing needs restoring.
- Rollback of a running session: clear the boot argument (or set the sysctl back), then re-run
  `tools/phx_baseline.sh` and confirm the numbers returned to the phase-1 row.
- The existing display-level kill switch stays: `$G/phxboot-off` stops the arming, and `nvram -d
  phxfb-boot` leaves the next boot on the firmware framebuffer (`tools/phxctl/phxboot.sh:8`, `35-41`).
- Constraints from the work order: no BIOS or firmware change, no video decode, no external-display work,
  and no change to how the GPU is brought up. Files derived from NullMoth (`src/phxaccel/**`,
  `src/nmplugin/**`) keep `LICENSE.PolyForm-NC`, their headers and `THIRD_PARTY_NOTICES.md` untouched.

## 9. Thresholds the verdict uses

`tools/phx_baseline_report.py` applies these numbers (its `THRESHOLDS` table is the same set) and prints
them next to every decision, so a reader can disagree with the verdict by disagreeing with one number
instead of re-deriving it. Median over the capture's windows; a capture with one window is provisional.

| hypothesis | supported when | refuted when | undecidable when |
| --- | --- | --- | --- |
| H1 (the copy limits the present rate) | `copy_share_of_refresh_pct` ≥ 40 and `presents_per_s` ≤ 0.85 × `vbl_hz` | either condition fails | never (both are always captured) |
| H2 (the software tick's jitter causes judder) | `vbl_late_avg_us` ≥ 300 or `vbl_late_max_us` ≥ 2000 — reported as a **candidate**, since the B2 A/B is what shows it costs frames | both below | never |
| H3 (the cadence is uneven rather than slow) | `presents_per_s` > 1.05 × `vbl_hz` (more presents than refreshes: the duplicate-present bug) or the share of copies landing two or more refreshes after the previous one ≥ 5 % | both below | the capture has no `iop_gap*`/`iop_vsync_*` fields |
| H4 (surface readiness stalls show up as repeated frames) | `copy_skip` ÷ (`on-panel` + `copy_skip`) ≥ 3 %, or the blank-frame share ≥ 3 % | both below | never |

40 % of a refresh, 5 % of copies and 3 % of frames are order-of-magnitude lines, not physics: they separate
"the copy owns the refresh" from "the copy is an eighth of it". If a capture lands next to one of them, say
so in the record instead of reading the tool's word as a result.
