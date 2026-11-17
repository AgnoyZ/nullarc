# Original34 bounded complete-runtime probe

Status on 2026-11-17: preparation, CPU checks and a separate bounded
complete-runtime Vulkan compute GPU trial passed. Both whole-arena checks
passed after same-address IB bytes changed. Independent recovery and scope
retirement also passed. The explicit immutable-tail workaround remains
opt-in; the unmodified native single-IB path is not repaired by changing the
kernel. Original34 kernel, ABI, production helper, A1/A2/corrected-A3,
default waits and desktop HOLDs are unchanged. See the exact
[hardware scope and limits](#complete-runtime-hardware-result).

## Program and boundary

The probe loads the private four-file RADV library directly through its ICD
entrypoint. It installs no loader, ICD manifest or runtime. It requires one
physical device with PCI identity `1002:1900` and a compute-only queue; there
is no graphics/family-zero fallback. It refuses inherited driver/loader
overrides and sets the explicit tail only in the test process. WindowServer
remains excluded by the unchanged core policy.

The same primary Vulkan command buffer is reset and recorded twice. Push
constants change the four-word pattern, starting with `0x7800c0de` then
`0x7800c0df`. Four workgroups of 64 invocations write 256 words starting at
byte `0x2010` in a host-visible coherent GTT buffer. Each pass poisons that
output range and checks the complete 16-KiB arena after positive retirement;
all other bytes retain their guard value. Both Vulkan fence completion and
the actual native retirement observation must succeed before comparison,
reset, unmapping, freeing or closing.

A separate dependent guard dylib interposes the runtime's IOKit boundary.
Before loading RADV, an external null-service open must be blocked and the
guard's own invalid-handle forwarding check must complete without recursion
or a GPU client. Target constructor IOKit activity is rejected. After arming:

* Only one direct PhxBringup service under exactly one PCI `1002:1900` parent
  may be selected/opened. Matching/open retries, proxy fallback and another
  client are refused. The actual core and tail helper each send their existing
  Hello on that same connection; both must report original34, ABI 1.12, VMID 8
  and 64 IBs. QueryInfo requires native/S1B readiness without HUNG. Withdrawn
  kernel identities are rejected.
* Setup/teardown is shape- and resource-tracked. Read-only register/topology
  queries are bounded; scanout, desktop/proxy selectors and host imports are
  refused. The first BO is the private core tail. Its NOP and zero padding
  are checked before CPU unmap. CPU remapping is refused, and publication
  must request only read/execute flags.
* Both original34 canonical halves of the 48-bit VA space are checked for
  canonicality/overflow. Normalization occurs only in the guard's coverage
  and overlap observer; forwarded addresses/packets are untouched. Payload
  IBs require tracked executable GPU mappings and readable CPU backing.
* At most two native submissions are forwarded. Every IB is compute/instance
  zero/ring zero, with the private tail last. The observer copies actual first
  payload bytes. The second must reuse an IB address with changed bytes in
  their common extent; both lengths are recorded. Sequence progress or two
  matching outputs alone cannot satisfy this check.
* Errors, malformed/non-increasing sequences, inconsistent retirement, wrong
  values or unexpected resource changes enter HOLD. The process and BOs are
  retained for independent recovery. Original34 still lacks close-time
  quarantine; never kill a held native process as recovery.

This test boundary does not replace the kernel's checks or provide a general
security boundary. It neither initializes the GPU nor supplies an automatic
hardware launcher. A fresh frozen scope must independently verify the exact
original image, protected files, EFI/security state and live independent
deadline; allow one initialization/one executing client/two native submissions;
then recover once to GPU-off/firmware framebuffer. Consumed scopes cannot be
reused. No extra precheck client or automatic retry is permitted. Rollback
changes no persistent runtime file and uses that separate recovery path.

## CPU evidence and limits

The actual complete Vulkan program ran against the private RADV release dylib
with guard platform ops replaced at compile time by CPU-only ops. An explicit
output oracle writes expected arena bytes; it is not a shader ISA, cache,
coherency or GPU timing model. The actual driver still performs enumeration,
logical-device creation, ACO compilation, command recording/reset, CS/transport
submission and synchronization. The final normal case observed one open/close,
two fake submissions, two whole-arena checks, the tail and changed bytes at
the same IB address. Both IB lengths were 256 bytes. Its `CPU_platform=1`
result cannot be parsed as a native hardware pass.

All 15 complete-program CPU cases passed: normal execution, missing target,
withdrawn identities, wrong minor, HUNG, allocation error/bad geometry, either
submit failing, zero sequence, wait error/bad retirement, stale pass-zero output
and guard-byte corruption. Only verified CPU fixture processes are terminated
after expected HOLD; the harness cannot run the native platform build.

Another 25 ASan/UBSan cases compile the actual guard directly with CPU ops.
They cover low/high canonical positives; proxy/repeated opening/enumeration;
extra Hello; NOP/padding corruption, tail remapping/writeability; noncanonical
and overlapping maps; graphics/unknown IB mapping; missing submit output,
excess IBs and scanout; in-flight close/free/unmapping; unchanged second IB
and a third submit. Rejected calls cannot advance the guarded boundary.
The probe, guard and CPU platform are sanitizer-instrumented in CPU tests;
the complete release RADV is not. The known profile sync-clone orphan remains
recorded and unfixed.

Early CPU preparations exposed overly narrow test assumptions: one Hello
rather than the core and tail helper's two on the same connection, and low-only
VAs rather than original34's two canonical halves. Corrections followed the
actual source without changing the driver or client limit. The first shader
used dynamic push-constant indexing, so changed parameters could leave IB bytes
unchanged. Static component reads now permit inline constants; the observer
confirms actual same-address byte changes. Earlier preparations are not counted
as passes or eligible native candidates.

The final native probe/guard were separately compiled without CPU platform
symbols, signed and verified as x86_64. The preparation commands executed only
their no-client guard self-test, as recorded in the immutable
[sanitized preparation record](validation/build34-radv-runtime-probe-offline-20261117.json).
That historical CPU/preparation record is separate from the subsequent GPU
trial below. These commands publish no binary or extend artifact exceptions.

## Complete-runtime hardware result

A fresh scope on macOS 26.7.2, build 25G332, tested source commit
`c73d5cd38bba8003ac5f7d71dc2a0c6cca80aa6f` against the exact original34
image. The complete private RADV library had SHA256
`3ee77d9b0dd71c9209ab1f60e6441a64ed66d680a6a239104dd1fd459be30219`.
The actual Vulkan enumeration, logical-device creation, ACO compilation,
command recording/reset, compute queue submission, fence waits and destruction
ran on the native platform. The result explicitly reported `CPU_platform=0`.

The observer verified one executing client open and close, two native
submissions, an immutable last tail and changed payload bytes at the same
IB address. Both IB payloads were 256 bytes. The first whole 16-KiB arena
matched `0x7800c0de` at `0x2010`, and the second matched `0x7800c0df`.
Vulkan completion and native sequence 1/retired 1, then sequence 2/retired 2,
were positive before comparison. There was no output or guard-byte mismatch.

One independent recovery reboot returned to GPU-off/firmware framebuffer;
there were zero GPU calls after recovery. Independent read-back verified 46
protected files, two links, all 347 EFI files (including 148 Microsoft files),
security and kernel collections unchanged, with no new matching diagnostic
report. The consumed launch job was removed. No driver or runtime was installed,
and no binary was uploaded.

An earlier fresh launcher scope failed before the original initializer could
start: its absolute path to the low-priority scheduling tool was wrong. It
executed no GPU initialization or Vulkan program. That scope recovered once,
was independently verified and retired, and was never replayed. The corrected
launcher uses the actual system tool path, pins both scheduling tools and
executes a harmless command as a CPU-only preflight. Its 12 controller tests
passed before preparing the new scope. The launcher failure is not a GPU
failure or a passing test, and the corrective scope retained the exact same
three native binary hashes.

See the [sanitized hardware record](validation/build34-radv-runtime-probe-hardware-20261117.json).
Together with the earlier same-binary failing single-IB/positive-tail
[transport comparison](validation/build34-radv-ib-tail-hardware-20261117.json),
this verifies the explicit-tail workaround through the bounded complete Vulkan
compute path. It does not prove the cache/root cause or repair the unmodified
kernel's single-IB behavior. Default policy remains unchanged. Graphics,
stress/concurrency, desktop, default waits and FPS have not been accepted;
the known profile sync-clone orphan is also unchanged. Those limits must not
be inferred away from two passing dispatches.
