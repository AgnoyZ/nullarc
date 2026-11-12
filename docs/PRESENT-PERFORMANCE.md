# Display-copy performance experiment — 2026-11-12

The reported symptom is an uneven, sluggish Hackintosh desktop. This source
experiment removes identifiable CPU-copy work. It does **not** establish that
the installed driver is this revision, that the target runs Tahoe, that GPU
acceleration works, or that its frame rate improves. The current editing host
is Windows; target OS version/build, active deployment and frame-time evidence
are still missing. HiDPI alone does not reduce the native backing raster.

## Changes, in priority order

1. **Do not transfer row padding.** `performTransaction` validates that source
   and destination strides are word-aligned and hold the visible width, then
   copies exactly `w` pixels per row. The former `min(pitches) / 4` copied
   padding whenever both layouts were padded. Source/destination row addressing
   still uses their own strides. A short row is refused rather than truncated.
   For a synthetic 2560×1600 layout with both strides 2624 pixels, this avoids
   409600 bytes of source reads and destination writes per frame. It saves
   nothing when both strides already equal 2560; it is not an FPS measurement.
2. **Batch packed SSE frames.** With the existing SSE knob enabled, addresses
   and strides eligible, identical visible/stride widths, and an integral
   number of 64-byte blocks, call the existing streaming assembly once for the
   entire frame. At 2560×1600, this reduces XMM save/restore sequences from 1600
   to one. The final `sfence` remains. Padded/misaligned frames and short tails
   retain the row/pair/word fallback. SSE remains default off; this does not
   remove a GPU fence, enable unsupported AMD zero-copy flips, or change VBL.
3. **Avoid invalid-shadow reads.** The first/invalid/forced damage copy already
   stores every group. It now skips comparison with the uninitialized/obsolete
   shadow and fills the shadow as before. Subsequent unchanged frames still
   store zero bytes; a changed short tail stores only its own group. Damage
   remains opt-in, with the existing busy/allocation-failure full-copy fallback.

These changes use existing downstream code; no external code or binary was
imported and licences/notices are unchanged. Revert the experiment's source
commit for rollback. No EFI, boot settings, OS security or deployed driver is
modified by repository work. Keep A/B variables separate: padding optimization
with SSE/damage off, packed batching with SSE on/damage off, damage separately.

## Host verification and limits

`python3 tools/test_present_copy.py --out build/present-copy` extracts the
**current actual** full-copy, damage-copy and streaming assembly bodies and
executes them on ordinary POSIX x86-64 host RAM with ASan/UBSan. A test-only
wrapper counts assembly calls without replacing the assembly. The independent
oracle checks both pixel formats, all destination words including padding and
guard regions, unchanged source data, alignments, different strides, short
tails, native raster, forced/unchanged/changed damage frames, shadow
disable/re-enable, busy and allocation-failure fallback. The allocator is
deliberately uninitialized. `--sanitizer memory` is available on hosts with
MemorySanitizer. No MemorySanitizer result is implied by ASan/UBSan.

Inline assembly memory accesses are not sanitizer-instrumented; guard/padding
comparisons are necessary in addition to sanitizers. Fake atomics/allocators
do not validate kernel concurrency. Tests cannot validate kernel FPU state
across preemption, write-combined/BAR throughput, real scanout or frame pacing.
Native kext compilation is a separate focused CI step, not target execution.
`tests/test_copy_path.cpp` additionally checks width/stride refusal, packed
size overflow, selection and fallback boundaries. Windows only runs Python
extraction/refusal checks; native cases are explicitly skipped there.

Focused run `43126365088` passed on Linux and Intel macOS; results and limits
are recorded in `validation/present-copy-20261112.md`. Never substitute
operation counts for a target frame-rate claim.

## Target measurement needed next

In the Hackintosh checkout, record these read-only version fields, then run the
existing read-only capture while repeating the same window drag/scroll task:

```sh
sysctl -n kern.osproductversion kern.osversion
sh tools/phx_baseline.sh --out /Users/Shared/phx-before --window 20 --samples 3
python3 tools/phx_baseline_report.py before=/Users/Shared/phx-before
```

Use a fresh output directory each time. Python is needed only for the report,
not capture. Start without changing settings or installing this experiment.
If capture reports a missing driver counter, record the named error: it cannot
diagnose another driver's graphics path, and absence is not proof of this
driver's performance. Check the active driver/build before applying changes.

After a separately reviewed installation with rollback, repeat as `phx-after`
with the same refresh, physical raster, workload and knobs. Compare:

```sh
python3 tools/phx_baseline_report.py before=/Users/Shared/phx-before after=/Users/Shared/phx-after
```

Priorities depend on actual evidence: copy-dominated frames require checking
the verified RAM alias and copy cost; VBL lateness requires timer evidence;
copy skips require surface/GPU readiness investigation. Retain synchronization
and software escape limits. Report present rate and cadence separately from
real GPU execution and physical panel refresh. The existing counters provide
aggregate cadence evidence, **not** per-frame p95/p99 or proof of stable FPS.
Keep local capture directories/raw logs private and out of commits. Share the
OS version/build, relevant counters and derived verdict after privacy review.
