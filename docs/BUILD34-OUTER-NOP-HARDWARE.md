# Original34 outer-NOP hardware comparison

Status on 2026-11-17: **fresh original and equal-footprint outer-NOP scopes
both reproduced the native single-IB wrong value; both independently recovered
and retired**. The NOP prefix is rejected as a repair. The original kernel,
helper, ABI and A1/A2/corrected-A3 source remain unchanged. Desktop, default
waits, stability and FPS remain on HOLD.

This follows the [three-policy preparation](BUILD34-OUTER-MEMSYNC.md). The
owner authorized the internal-disk experiment. Actual OS was macOS **26.7.2,
build 25G332**. Both scopes pinned source commit
`54cf5c38a0b3a9ed8a09bd1d0d9213be0b5a0d39` and used the same signed probe
with `--run-single`. The original executable SHA-256 was
`4a88035fd2ead990b8c44b638c9283d579b14d6ba4f0b48d78d6435a3a44a412`;
the NOP executable SHA-256 was
`3124e6378ef7d3c7c04ec84aa69a724e67f70c2e5ab8c3cc00ed45b50b81d543`.
Full bundle metadata matched the original control. Private Mach-O identities,
not the build34 label alone, determined loaded-image admission.

## Execution and observation

Each fresh one-use scope allowed one initializer, one probe client, at most
two native submissions, an independent 300-second deadline, one recovery
reboot and no automatic retry. The original control was independently
recovered and retired before candidate activation. On the candidate boot,
the restore-only job first restored the exact original image to disk.
Independent startup read-back verified the NOP image loaded, original image
on disk, recovery backup intact and GPU still off before the candidate scope
was prepared and separately admitted.

Both initializers passed. Both probes passed the first complete 16-KiB arena
check and failed the second dispatch at **`0x2010`: actual `0xde`, expected
`0xdf`**. Both retained all 256 output words from the previous pattern; no
output word matched the current pattern or poison, and no shader-page,
command-page or guard mismatch was found. The observation reads saw no byte
change. Native wait completion did not imply correct output. The failed
probe retained its resources until the single recovery reboot; no held GPU
process was killed or retried.

The candidate controller completed collection without an exception and
reported `expected_comparison_observation: false`, because its pass condition
required two successful whole-arena checks. Its failure and independent
reparse are retained; this is a rejected candidate, not a successful GPU
trial. The precise failure does satisfy the narrower prerequisite for a
separate equal-footprint ACQUIRE comparison. It does not prove a CP/cache
root cause, establish that all padding is ineffective, or authorize reuse of
either consumed scope.

## Observer serialization and final recovery

The new frozen route and scope helpers shared one secure bounded EFI mount
lock across each entire mount/verify/write/unmount lifecycle. Six CPU
filesystem tests covered actual two-process exclusion, timeout, unsafe
symlink/hardlink/mode refusal and exception release. Together with 16 bundle
swap, 12 route/startup and 24 scope/parser tests, 58 CPU methods passed; the
candidate configuration also passed its separate 24-method controller suite.
No CPU test is GPU evidence. The preceding comparison's mounted-EFI observer
refusal did not recur in this comparison.

Independent post-recovery verification checked original34 loaded, NOP image
absent, GPU off and firmware framebuffer only. Both consumed test jobs and
the restore-only job were removed. Cleanup verified the exact nine-file
dedicated recovery subtree before removing it; a separate read-back then
matched all **347** original EFI files. All **46** protected files, protected
links, security settings and kernel collections were unchanged. No new
matching diagnostic report was found, EFI was unmounted, and no trial job,
GPU client or held process remained.

The Windows fallback script was retained for the trial but was not executed
in Windows; no compatibility or pre-OS automatic-recovery claim is made.
No working EFI configuration, Windows EFI, partition, NVRAM, BIOS or security
setting was changed. No binary or raw diagnostic was published.

The [aggregate hardware record](validation/build34-outer-nop-hardware-20261117.json)
contains only public hashes and bounded observations. At this checkpoint the
ACQUIRE image remains privately built and statically checked, **not installed,
loaded or GPU-tested**. A later ACQUIRE comparison requires a new frozen route,
independent recovery checks and a fresh one-use scope; none is armed by this
record. Original34 admission and all existing HOLDs remain.
