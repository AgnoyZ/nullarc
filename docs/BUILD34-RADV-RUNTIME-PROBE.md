# Original34 bounded complete-runtime probe

Status on 2026-11-17: preparation and CPU checks passed. No complete-runtime
GPU trial has been armed or executed by this addition. The original34 kernel,
ABI, production helper, A1/A2/corrected-A3, default waits and desktop HOLDs are
unchanged. The earlier [bounded transport comparison](BUILD34-RADV-IB-TAIL.md)
does not substitute for executing this complete Vulkan path on hardware.

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
symbols, signed and verified as x86_64. Only their no-client guard self-test
was executed. See the [sanitized preparation record](validation/build34-radv-runtime-probe-offline-20261117.json).
There is no complete-runtime GPU, graphics, desktop, performance or FPS
acceptance. These commands publish no binary or extend artifact exceptions.
