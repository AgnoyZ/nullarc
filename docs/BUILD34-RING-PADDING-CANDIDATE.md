# Privately built original34-derived ring-padding candidate

On 2026-11-17 the owner continued the
[source proposal](BUILD34-RING-PADDING-PROPOSAL.md). An isolated experimental
kext was compiled and statically verified in ignored private build storage.
**It has not been installed, loaded, initialized or tested on the GPU.** The
native single-IB wrong value remains unresolved; desktop/default-wait/FPS
HOLDs remain in place. This is not the untouched original34 image.

## Source and build boundary

`tools/upstream34_layout/ring_padding_candidate.py` verifies the approved
checkpoint `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c` inputs, then applies
only the two reviewed `gpuSubmit` source edits in a fresh private directory.
The full candidate driver source SHA-256 remains
`b34f262fe5cd05b6aa8b18d9500a23121e838dea0c3ffb86cf63f74fbdfc06c0`;
the exact CPU-tested function has not changed. Original production source,
ABI, helper, A1/A2/corrected-A3 and original-image admission are untouched.
Neither withdrawn build41 nor build42 is prepared or used.

The builder requires the independent MacKernelSDK checkout at
`3f750085caa17ec3a7880f11c11bf4f48cd6a164`. It checks that Git is reporting
that checkout itself, rejects dirty scoped inputs, and verifies all 1,216
archived source/library/notice files against the pinned Git blobs before
materializing them. Archive paths, duplicates, links and unexpected entries
are rejected. The SDK's notices stay with its private snapshot. No SDK files
or runtime binaries are published.

The unchanged original `src/phxbringup/build.sh` runs only inside the new
private source snapshot. Its deletion of its own build directory cannot
reach an existing candidate or repository source. The compiler runs serially
at low background priority with a restricted environment. Compiler, linker,
Clang kernel runtime, libLTO, host-SDK settings and signing tools are hashed
before and after. `libkmod.a` belongs to the pinned MacKernelSDK; the existing
`-lcc_kext` link option resolves to Clang's own kernel runtime. No installer,
EFI helper, `kmutil load`, GPU initializer or native probe is invoked.

## Explicit packaging review

The first native build used the approved source Info.plist unchanged.
Independent read-back then found that the exact deployed original image
restricts `IOPCIMatch` to `0x19001002`, whereas source lists four PCI IDs.
The first read-back's metadata-equality assertion therefore failed; it did
not install or execute that image. The built artifact is retained as
superseded private history, not admitted for treatment.

The reviewed packaging step now narrows **only the fresh output bundle's**
PCI match to `0x19001002`. Its complete Info.plist SHA-256 is
`aaeef27a947e0a2a70b358628ff21216a5edaf0a5d65f32651f8654cef654af7`,
which an independent privileged read verified byte-for-byte against the
actual original-image control bundle. Bundle version and build marker are
unchanged. Repository source Info.plist and the frozen source copy remain
unchanged. This packaging restriction is an explicit addition to the initial
proposal, keeping the treatment's target matching equal to the real control.
It is not a broader device enablement or a change to the two tested function
edits. The bundle is signed only after applying the restriction.

The final signed candidate executable SHA-256 is
`58f7dab14e3e1768d0fca2333eedea7e15e51e3257c966c0430e46dfe304e8b3`.
Independent read-back verified that both this hash and the Mach-O image
identity differ from the exact original executable, whose SHA-256 remains
`4a88035fd2ead990b8c44b638c9283d579b14d6ba4f0b48d78d6435a3a44a412`.
Raw image identities remain private. A `phx-build=34` property, unchanged
version or matching identifier alone must never admit this derived image as
the original. Rebuilding requires fresh binary hashes and identity review;
these receipts describe this private artifact only.

## Validation and limitations

All 16 candidate preparation regression methods passed. They cover exact
complete source identity/reapplication refusal, the control-matching metadata
restriction, archive and SDK checkout integrity, private destination limits,
native-platform refusal, bundle links, x86_64 kext structure, and malformed,
missing, duplicate or zero Mach-O identities. These tests use CPU data and
fake subprocess results where appropriate; none builds or runs a driver.

The separate actual native build passed compilation, ad-hoc signing, strict
signature verification and x86_64 verification. Its bundle, source, recipes,
SDK files and toolchain hashes passed read-back. Three field-shadow warnings
were retained; an independent syntax-only compile of untouched original34
with the same headers/options emitted the same three warning messages.
No surrounding source was changed merely to remove those warnings.

The initial preflight incorrectly expected `libcc_kext.a` inside MacKernelSDK
and stopped before source materialization or compilation. That input check
was corrected to record Clang's actual runtime separately. The next native
build succeeded but was superseded for the explicit target-match packaging
review above. A fresh final build passed after that review. All attempts and
raw logs stay private. See the
[sanitized build evidence](validation/build34-ring-padding-candidate-offline-20261117.json).

```sh
nice -n 15 /usr/sbin/taskpolicy -b python3 -B -m unittest discover \
  -s tests -p test_upstream34_ring_padding_candidate.py -v
nice -n 15 /usr/sbin/taskpolicy -b python3 -B \
  tools/upstream34_layout/ring_padding_candidate.py \
  --sdk /path/to/reviewed/MacKernelSDK \
  --out build/fresh-ring-padding-candidate-private
```

The earlier 72,222 actual-function CPU scenarios remain source-level
evidence, not GPU acceptance. The actual OS observed during this preparation
was macOS 26.7.2, build 25G332. No claim about GPU correctness, graphics,
stability or frame rate follows from compiling on it.

## Remaining live-test gate

A subsequent [read-only loading-route audit](BUILD34-RING-PADDING-LOAD-ROUTE.md)
confirmed the exact original image in the running boot collection and the
candidate still uninstalled. It did not establish a runtime replacement or
exact-original recovery route; those must be resolved before consuming a new
control. No live unload, EFI write, GPU work or reboot was attempted.

No new hardware scope or loaded-image admission has been prepared or armed.
The proposal's separate fresh original-image reproduction control,
candidate-specific admission, exact-image rollback, independent witnesses,
deadlines, recovery and consumed-job retirement remain necessary. A distinct
candidate identity and equal metadata are prerequisites, not authorization or
evidence that installation/recovery is ready. Do not replay any consumed
scope or weaken the original-image gate. Any actual trial must preserve the
one-initialization/one-execution-client/two-submit limits and must never kill
the held native process as cleanup. Binary distribution remains blocked for
this private experiment; only reviewed source and aggregate evidence are
synchronized here.
