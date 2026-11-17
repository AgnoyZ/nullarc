# Original34-derived compute-ring padding proposal

Status: **hardware scope inactive**. Subsequent owner continuation produced a
[privately built derived candidate](BUILD34-RING-PADDING-CANDIDATE.md), with
an explicitly reviewed output-bundle target restriction matching the actual
original-image control. It has not been installed or loaded. The initial
source proposal below remains the boundary for the two function edits.
The original native single-IB defect remains unresolved. The
[CPU-only audit](BUILD34-RING-PADDING-AUDIT.md) has passed, including the
revised order that keeps RELEASE_MEM last. This proposal defines the next
comparison without treating a changed kernel as the untouched original34.

## Exact source boundary

Start from the default branch `upstream34/vram-layout-fix`, preserving the
approved checkpoint `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c` and A1/A2/
corrected-A3. The two-site transformation is the one tested in `d9aa254`:

1. Acquire the existing submit lock before calculating the exact compute-ring
   reservation, retaining the original 16-dword guard and unlocking on refusal.
2. Insert single-word compute NOPs after the IB descriptors and before the
   final eight-dword RELEASE_MEM so the published end is 256-dword aligned.

Graphics uses its original unpadded reservation and packet sequence. Queue
selection/fallback, VM binding, IB descriptors, sequence allocation, fence
payload, history publication, flushes and doorbell writes otherwise remain
unchanged. No wait, ABI, initialization, hang-recovery, plugin or runtime
change belongs in this experiment. The source-defined compute ring is 1024
dwords with initial WPTR 8; do not substitute the query's hardcoded 4096 for
that geometry.

The original complete driver source SHA-256 is
`beffab5dc13e4018ff2ab9f90c82d85c0982ce7e3563e3175999399c7bc083e5`.
Applying only the tested transformation in memory gives source SHA-256
`b34f262fe5cd05b6aa8b18d9500a23121e838dea0c3ffb86cf63f74fbdfc06c0`.
Its `gpuSubmit` SHA-256 is
`c0d916882adaec32e928f17979cb05f671ad540122642a6b600aa88c02146a02`.
The complete reversible diff SHA-256 and protected original inputs are in the
[source proposal record](validation/build34-ring-padding-source-proposal-20261117.json).
No driver source file was materialized or changed to obtain those initial
proposal hashes. Subsequent private build materialization is recorded in the
linked candidate preparation; repository production source remains unchanged.

The existing recipe can regenerate this exact function for inspection; it
does not build a kext. The separate candidate builder produces an
**original34-derived experimental image**, not the already accepted original
image. Any source or
metadata difference beyond this proposal needs its own review and fresh
hashes; it cannot silently inherit this CPU evidence.

## Before a modified-image test can be armed

- Freeze and review the isolated candidate source and build inputs; verify
  the original source, ABI and production helper remain available unchanged.
  Build41/build42 are excluded.
- Pin the actual candidate binary, bundle, signature and loaded-image
  identity separately from the untouched original34. The private build now
  records these values and independent static comparison; live candidate
  admission is still unprepared. A version string or matching bundle identifier is insufficient.
  Preserve the original image's admission checks; use a separate
  candidate-specific gate that rejects the original or any other image.
- Review the scope against actual ring geometry. The CPU accounting fits
  an empty 1024-dword compute ring, but small admitted ring geometries can
  refuse more submissions. Do not promote this as a general compatibility
  fix or alter queue admission to conceal that difference.
- Review and CPU-test new one-use control/treatment controllers, result
  parsing, independent witness/deadline, rollback and recovery verification.
  Freeze explicit deadlines before arming. Existing consumed scopes, their
  jobs and their original-image receipts cannot admit this candidate.
- Verify a tested path to restoring the exact original image without EFI,
  NVRAM, BIOS, disk-layout or security-policy changes. If candidate recovery
  cannot fit the one-recovery-reboot limit, redesign it before arming.

This source proposal does not install a kernel, alter admission, create a
launch job, authorize GPU execution or request a reboot.

## Proposed comparison and ordering

Use the same already signed diagnostic for both images, with binary SHA-256
`f89035937656ecc16cf6329a24801e29b8cd40d3c646e66d03628b358a9703a5`,
and its existing `--run-single` mode. It uses one payload IB descriptor and
rewrites the same command memory between two guarded dispatches. Do not add
an immutable tail, ACQUIRE_MEM, a delayed resample, another output target or
different native waits to this comparison. The binary was hashed, not
executed, while preparing this proposal.

1. In a **new original-image control scope**, admit only the exact untouched
   original34. Allow one initialization, one execution client and at most two
   native submits. Require pass 0's whole-arena check and reproduction of the
   precise second-pass `0x2010` mismatch (`0xde` actual, `0xdf` expected).
   Preserve that GPU failure as failure. If the control does not reproduce,
   stop the comparison; do not proceed automatically to the candidate.
2. Independently restore GPU-off/firmware-framebuffer state, verify protected
   files and security/KC state, and retire the control's consumed job before
   preparing treatment. A control observation alone does not establish
   successful recovery.
3. Only under a **separate fresh candidate-image scope**, admit the exact
   reviewed derived image and the same probe. Keep the original initializer
   and the same one-client/two-submit limit. The only experimental variable
   is the pinned compute-ring submission framing change.
4. Require both whole-arena dispatch checks, correct native sequence/fence
   observations and the independent witness's complete result. Then restore
   the untouched original image and GPU-off state and independently verify
   recovery and consumed-job retirement. Permit at most one recovery reboot
   per scope and no automatic retry. A mismatch, timeout, identity drift or
   incomplete witness is failure/HOLD, not success.

The held native GPU process must never be killed or terminated as cleanup.
Keep raw diagnostics, image identities and machine-specific recovery material
private. Preserve the original binaries, exact restoration path and privacy
checks; publish only reviewed aggregate results and source evidence.

Even a successful candidate scope would establish only this bounded compute
comparison. It would not validate graphics, WindowServer, desktop takeover,
FPS, default waits, general ring compatibility or arbitrary workloads.
Default promotion remains separate from this inactive proposal.
