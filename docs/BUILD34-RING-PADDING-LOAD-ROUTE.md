# Ring-padding candidate: read-only loading-route audit

Status on 2026-11-17: **candidate uninstalled; image-switch and recovery route
not established**. The [private candidate](BUILD34-RING-PADDING-CANDIDATE.md)
remains available, but its compilation is not a live-test admission. No new
control or treatment scope was prepared or armed during this audit. The native
single-IB wrong value remains unresolved.

## Fresh local observations

Privileged read-back on macOS 26.7.2 / 25G332 established:

- The loaded image matches the exact original34 executable. Its protected
  bundle is unchanged; the derived candidate is not loaded.
- There is one build34 service with no client children, no matching held probe
  or initializer process, and no remaining one-use test job.
- GPU-off is present. There is one firmware framebuffer, no accelerated
  framebuffer/accelerator service, and no display-arm or pending marker.
- All 46 protected files, protected links, security settings and the three
  kernel collections match the preceding recovered and retired scope.
- `kmutil showloaded` lists the original in the **boot** collection, not the
  system or auxiliary collection. Inspecting the on-disk collections does not
  list that injected image. Absence from on-disk inspection therefore must not
  be interpreted as absence from the running kernel.
- A fresh read-only EFI manifest comparison passed and the volume was
  unmounted afterward. Its active bring-up executable matches the original.
  This audit made no EFI write.

Original executable SHA-256:
`4a88035fd2ead990b8c44b638c9283d579b14d6ba4f0b48d78d6435a3a44a412`.
Candidate executable SHA-256:
`58f7dab14e3e1768d0fca2333eedea7e15e51e3257c966c0430e46dfe304e8b3`.
Exact image identities, EFI manifests, paths and raw command output remain
private. See the [aggregate record](validation/build34-ring-padding-load-route-readonly-20261117.json).

## Why runtime replacement is not admitted

The deployed Info.plist lacks both `OSBundleAllowUserLoad` and
`OSMutableSegmentCopy`, including their x86_64-specific forms. In Apple's
public XNU snapshot
[`f6217f891ac0bb64f3d375211650a4c1ff8ca1ea`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libkern/c%2B%2B/OSKext.cpp#L2264-L2293),
the primary-collection initialization sets `unloadUnsupported` unless one of
those properties is true. Its
[`OSKext::removeKext`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/libkern/c%2B%2B/OSKext.cpp#L4605-L4625)
rejects that flag before service termination.

This is a pinned public-source comparison, **not proof of the running kernel's
internal flag**. The inspected snapshot is not asserted byte-identical to the
running kernel, and bundle properties alone do not establish all injected
runtime metadata. No unload attempt was made to resolve that uncertainty.
The observation is sufficient to reject an assumed, unreviewed
`kmutil unload/load` treatment route. No such command, service termination,
alternate-identifier driver or admission bypass was attempted.

Changing the candidate's identity, classes, load policy, boot configuration or
kernel collection would add a separate variable and cannot silently inherit
the existing two-edit experiment or exact-original admission. The repository's
working-EFI and security boundaries remain in effect.

## Concrete prerequisite before spending a new GPU scope

Establish and separately review a boot-image test route first. One possible
route is an independent test boot environment that leaves the working EFI and
normal original-image boot intact. It is a proposal only: no spare boot device,
test EFI, one-time boot selection or automatic return to the original has been
verified or prepared. A normal reboot currently has no established mechanism
to select the candidate. A recovery reboot from a future test environment must
not be assumed to select the original either.

Before arming, that route must pin the exact candidate and original images,
show how a single recovery reboot returns to the original and GPU-off state,
and provide independent loaded-image admission, deadline/witness and retirement.
Any EFI/boot-image deployment needs a separately defined authorization scope;
this read-only audit does not grant one. Do not change NVRAM, security policy,
the normal working EFI or protected KCs to work around this gate.

Only after this prerequisite is resolved should the
[existing comparison order](BUILD34-RING-PADDING-PROPOSAL.md#proposed-comparison-and-ordering)
consume a fresh original-image control: one initialization, one execution
client and at most two submits, retaining the precise second-pass failure.
Independent recovery and retirement must finish before a separate candidate
scope. Neither an old reproduction receipt nor this read-only audit admits
the candidate. Held GPU processes must never be killed as cleanup.

## Checks and outcome

The existing 16 candidate-preparation and six ring-padding recipe test methods
passed again at low background priority. They remain CPU checks; the earlier
72,222-scenario actual-function run was not repeated or counted as new evidence.
Production kernel/helper/ABI, A1/A2/corrected-A3, licenses and existing candidate
bytes are unchanged. No new kernel was built, installed or loaded, no GPU work
or reboot was requested, and no consumed scope was replayed. Graphics, desktop,
default-wait and FPS HOLDs remain.
