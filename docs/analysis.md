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

`nvAccelIopFlip()` (`src/phxaccel/accel/nvrm-accel.cpp:2107-2167`) is the zero-copy path — scan the
surface out of its own VRAM, no copy. It refuses this framebuffer outright:

```c
// zero-copy scan-out is an NVIDIA display-engine flip; another vendor's panel (NMIntelFB) always takes the copy
if (!fb->metaCast("NVRMNVDAFramebuffer")) return false;      // nvrm-accel.cpp:2110-2111
```

So on the 780M **every presented frame costs a CPU copy** (`performTransaction`,
`nvrm-accel.cpp:1110-1266`). Any smoothness work here is work on the copy path; "turn on zero-copy" is not
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

`performTransaction` picks the source, then copies one row at a time (`nvrm-accel.cpp:1211-1240`):

- source: our VRAM resource (`nvrm-accel.cpp:1138-1145`), else the IOSurface's system memory
  (`nvrm-accel.cpp:1149-1168`, after `nvAccelSurfCopyReady` and `nvSurfWaitReady`).
- narrowed formats: WindowServer moves to 10-bit `l10r` (ARGB2101010) once colour management is up and the
  panel is 8-bit XRGB, so those frames lose two bits per channel while copied
  (`nvrm-accel.cpp:1156-1160`, `1226`, `1237`).
- inner loop: 8-byte `movnti` pairs by default; a 64-byte SSE4.1 row (movntdqa/movntdq) only when
  `debug.nvaccel_iop_sse=1` (`nvrm-accel.cpp:1209-1233`, row routine `1042-1086`). Measured in the code's
  own comments: 1.0 ms per frame with SSE against 2.1 ms without (`tools/phxctl/phxboot.sh:63-64`), and
  plain loads on a write-combined surface read at ~0.5 GB/s, 13-30 ms per frame
  (`nvrm-accel.cpp:1032-1034`).
- the SSE routine saves ten XMM registers around every row because x86 XNU switches the FPU lazily and the
  preempted thread may be a user thread whose registers the kernel does not save
  (`nvrm-accel.cpp:1035-1040`) — per-row overhead that today is paid per row, not per frame.
- `sfence` before the transaction is reported complete (`nvrm-accel.cpp:1241`): the frame must be in DRAM
  before the panel may read it.

### 1.4 Present pacing

A copied frame is reported complete on the **next** VBL tick, as a flip would latch
(`nvrm-accel.cpp:1087-1093`, gate in `isTransactionComplete`, `nvrm-accel.cpp:1095-1103`). The reason is
recorded in the code: completing immediately let WindowServer present twice inside one refresh and then
skip the next — "frames 3-4 ms apart followed by 12-16 ms gaps, 97 presents a second on a 120 Hz panel"
(`nvrm-accel.cpp:1087-1089`). `debug.nvaccel_iop_vsync` defaults to 0 and `tools/phxctl/phxboot.sh:67`
turns it on for the armed panel; past two refreshes a pending transaction completes anyway
(`nvrm-accel.cpp:1100`), so a broken VBL cannot freeze the desktop.

There is also a per-head hold: at most four frames in a row are kept off the panel when the surface's
newest pixels are still only in VRAM (`nvAccelSurfCopyReady`, `nvrm-accel.cpp:2221-2253`), so a surface
that never syncs is copied stale rather than freezing the display.

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
  IOSurface → NVResource mapping (`2107-2130`), `NVAccelSurfaceWait` tells the plugin that `pageoff` waits
  for WindowServer's GPU writes (`nvrm-accel.cpp:670-674`), `nvAccelSurfScanoutSync`/`CopyReady` move the
  newest pixels to system memory before a copy (`2202-2253`), and a surface keeps its VRAM across the
  family's free/alloc (`debug.nvaccel_vm_sticky`, counters `nvaccel_vm_parked`/`_unparked`,
  `nvrm-accel.cpp:1312-1315`).

None of these decide smoothness by themselves; they decide whether a frame can be copied at all without a
stall. The per-frame cost they produce is measured only through the counters in §4.

## 4. The counters that already exist (nothing new is needed to measure phase 1)

| sysctl | meaning | where |
| --- | --- | --- |
| `debug.phxfb_alias` (rw) | 1 = copy through the carve-out, 0 = through the BAR | `phxfb.cpp:32-35` |
| `debug.phxfb_vbl_staged` (rw) | 1 = staged VBL arming, 0 = one plain deadline | `phxfb.cpp:47-48` |
| `debug.phxfb_vbl_n`, `_late_us_sum`, `_late_us_max` | ticks fired; lateness summed / worst | `phxfb.cpp:49-51` |
| `debug.nvaccel_iop` (rw) | 1 = publish display-pipe capabilities and run transactions | `nvrm-accel.cpp:1291-1293` |
| `debug.nvaccel_iop_sse` (rw) | 1 = 64-byte SSE row copy, 0 = 8-byte loads | `nvrm-accel.cpp:1342` |
| `debug.nvaccel_iop_vsync` (rw) | 1 = complete a copied frame on the next tick | `nvrm-accel.cpp:1087-1103` |
| `debug.nvaccel_iop_ok`, `_ok_h0..h4` | frames copied to a panel, per head | `nvrm-accel.cpp:1321-1326` |
| `debug.nvaccel_iop_src_res` / `_src_surf` | frames sourced from our VRAM / the IOSurface | `nvrm-accel.cpp:1336-1337` |
| `debug.nvaccel_iop_copy_skip`, `_blank` | frames held back / copied frames that were one colour | `nvrm-accel.cpp:1338-1340` |
| `debug.nvaccel_iop_copy_us`, `_max`, `_sum` | cost of the last / slowest / all copied frames | `nvrm-accel.cpp:1344-1346` |
| `debug.nvaccel_iop_bench`, `_read_us` | one timed read-only pass over the next source | `nvrm-accel.cpp:1341`, `1185-1193` |
| `debug.phxbos_flush` (rw) | BO cache maintenance per submit/wait: 0 none, 1 clflushopt, 2 clflush | `src/phxbringup/PhxBringup.cpp:35-43` |

`debug.phxbos_flush` matters to compositing too: with `clflush`, "WindowServer spent ~73% of its CPU here
and composited ~13 fps; with none, 41 fps" (`PhxBringup.cpp:35-38`) — the default is 0, and
`tools/phxctl/phxboot.sh:51-53` sets it explicitly.

## 5. Hypotheses

The work order refers to H1–H4 but neither the issue nor the repository defines them. These are the four
that the code above makes testable; **they are proposals for the owner to confirm, not the H1–H4 that were
asked for**.

| id | hypothesis | decides it | code it would touch | if false |
| --- | --- | --- | --- | --- |
| H1 | The copy cost, not the panel rate, limits present rate: one copied frame is a large share of a refresh and frames reach the panel slower than the VBL ticks | `copy_share_of_refresh_pct` and `presents_per_s` vs `vbl_hz` from `phx_baseline.sh` | copy loop `nvrm-accel.cpp:1211-1240`; destination `phxfb.cpp:434-451` | no copy optimisation: cost is not the limiter |
| H2 | The software VBL's jitter (not the copy) is the judder source, so presents land on the wrong side of a refresh | `vbl_late_avg_us`/`vbl_late_max_us`, and the A/B with `debug.phxfb_vbl_staged=0` | `vblFire`, `phxfb.cpp:218-242` | leave the tick alone |
| H3 | Present pacing is wrong rather than slow: duplicate presents inside one refresh followed by a gap | gap buckets `gCntIopGap[4]` (`nvrm-accel.cpp:1195-1204`) plus `copy_skip`/`blank`, A/B on `nvaccel_iop_vsync` | `isTransactionComplete`, `1095-1103` | pacing is not the problem |
| H4 | Surface readiness stalls are showing up as repeated frames | `debug.nvaccel_iop_copy_skip`, `nvaccel_iop_blank`, `nvaccel_vm_parked`/`_unparked` | `nvAccelSurfCopyReady`, `2221-2253`; sticky VRAM `1312-1315` | no readiness work |

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

What this change *does* add: this analysis, and `tools/phx_baseline.sh` — the read-only capture that makes
phase 1 a command instead of a discussion.

## 7. Phase 1, exactly

```sh
# on the target laptop, from a normal session, with the accelerated panel up
sh tools/phx_baseline.sh --out /Users/Shared/phx-baseline-$(date +%Y%m%d-%H%M) --window 60 --samples 3
sh tools/phx_baseline.sh --out /Users/Shared/phx-baseline-snapshot   # counters once, no window
```

Record, in one place, for each of the three windows: which destination was live (`debug.phxfb_alias`, and
`alias:` lines in the kernel log), `vbl_hz`, `presents_per_s`, `avg_copy_us`,
`copy_share_of_refresh_pct`, `copy_skip`, `blank_frames`, `vbl_late_avg_us`/`_max`. Then repeat the
60 s window three times with the A/B switches, one at a time, changing nothing else:

| run | change | question |
| --- | --- | --- |
| B1 | `debug.nvaccel_iop_sse=0` (versus the arming default of 1) | how much of the copy cost is the row copy |
| B2 | `debug.phxfb_vbl_staged=0` | is the staged tick worth it, and how late is a plain deadline |
| B3 | `debug.nvaccel_iop_vsync=0` | does the next-tick completion actually change the cadence |
| B4 | `debug.phxfb_alias=0` | the BAR copy baseline (expected to be much worse; it is the control, not a candidate) |

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
