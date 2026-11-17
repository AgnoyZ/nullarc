# Compute-ring padding: hardware comparison failed

On 2026-11-17 the fresh original-image control and the separate exact
ring-padding candidate both reproduced the same native single-IB failure on
macOS 26.7.2 / 25G332. Each passed the first whole-arena dispatch check, then
failed the second at `0x2010`: actual `0xde`, expected `0xdf`. **The proposed
compute-ring padding did not repair this reproducer and is not promoted.**
The default branch retains the original build34 kernel, ABI and helper,
including the accepted A1/A2/corrected-A3 source checkpoint. Build41/build42
were not used. Desktop, default-wait and FPS HOLDs remain.

## Exact comparison

Both scopes used the same signed probe
`f89035937656ecc16cf6329a24801e29b8cd40d3c646e66d03628b358a9703a5`
with `--run-single`, one initializer, one execution client and at most two
native submits. Neither scope added an immutable IB tail, changed output
targets or waits, or replayed a consumed scope. Each had an independent
300-second deadline and at most one recovery reboot without automatic retry.

| Image | Executable SHA-256 | Whole-arena checks passed | Second dispatch |
| --- | --- | --- | --- |
| Exact original34 | `4a88035fd2ead990b8c44b638c9283d579b14d6ba4f0b48d78d6435a3a44a412` | 1 of 2 | `0x2010`, `0xde` instead of `0xdf` |
| Original34-derived padding candidate | `58f7dab14e3e1768d0fca2333eedea7e15e51e3257c966c0430e46dfe304e8b3` | 1 of 2 | `0x2010`, `0xde` instead of `0xdf` |

Both failure snapshots classified all 256 output words as the previous
pattern, with 256 mismatching bytes. Shader, command and guard pages matched;
the two immediate observation reads did not change. The original mismatch
and held resources were retained until recovery, never converted to success
by a fence result or later observation. The probe's historical `original34`
output label did not identify the candidate: the outer controller admitted
the two exact loaded image identities separately. Raw identities and logs
remain private.

The [candidate's two source edits](BUILD34-RING-PADDING-PROPOSAL.md#exact-source-boundary)
and control-matching metadata were unchanged. This negative comparison shows
that this exact padded framing is insufficient for the reproducer. It does
not rule out every publication/cache interaction or establish the root cause.
The earlier immutable-tail transport/Vulkan results remain separate evidence;
they do not make this single-IB candidate a fix.

## Installation, recovery and retirement

The owner-authorized [internal-disk route](BUILD34-RING-PADDING-INTERNAL-TEST.md)
was used only after the fresh original control reproduced the fault,
independently recovered to original34/GPU-off and retired its consumed job.
Candidate activation and an independent read-back verified its exact bytes
on disk while the original was still loaded. One boot then loaded the exact
candidate. The restore-only startup job restored the exact original to disk
before any GPU initialization; an independent read-back verified the loaded
candidate, original disk image, backup and GPU-off state before preparing
the separate treatment scope. Candidate controller/parser CPU tests passed
all 24 methods for that new configuration before installation.

The candidate test preserved its failure and requested one recovery reboot.
On that new boot, the candidate recovery observer initially refused to check
an already mounted EFI volume while the restore-only startup observer also
accessed it. The mount refusal and raw traceback were retained. An independent
read subsequently verified a new boot, exact original loaded, candidate
absent, EFI unmounted, original disk manifest and GPU-off state. Only the
new-boot recovery-observation paths were then run serially; neither the
initializer nor probe was repeated. Final result verification reparsed the
original logs, retained the candidate failure and removed its consumed job.
Future startup observers need shared mount serialization; these frozen,
consumed packets must not be rearmed.

After both scopes were independently verified and retired, the restore-only
job and this trial's nine-file `EFI/OC/Nullarc34Rollback` subtree were removed
under exact-manifest checks. A separate final read-back confirmed:

- Exact original34 loaded; candidate absent; GPU-off and firmware framebuffer.
- All 347 original EFI files byte-identical, with EFI unmounted.
- No remaining trial/restore jobs, native clients or held test processes.
- All 46 protected files, protected links, security and kernel collections
  unchanged, and no new matching WindowServer/kernel/GPU-restart reports.

No normal boot configuration, Windows/fallback path, partition, NVRAM or
security setting was changed. The Windows rollback script was not executed
and remains unvalidated on Windows; no pre-OS automatic recovery claim is
made. Private root-owned evidence is retained, including the startup refusal
and independent recovery verification. No binary or raw diagnostic is
published. See the [aggregate hardware record](validation/build34-ring-padding-hardware-20261117.json).

## Outcome and next boundary

The native IB wrong value remains unresolved. Reject this candidate as a
repair; retain its source experiment and negative evidence as history.
Further work must derive a separately reviewed minimal change from default
build34, preserve exact-image admission and use fresh one-use scopes only
after the next offline hypothesis and recovery route are ready. There is no
armed follow-up GPU task and no graphics, desktop, stability or FPS acceptance.
