# Build34 complete R3 translation-unit check

November 21, 2026: the complete source-only R3 stage now compiles against the
reviewed native Kernel SDK. This closes a compilation prerequisite, **not R3
or native deployment admission**. The timer import audit independently refuses
admission because `_thread_call_cancel_wait` is only in the reviewed KDK's
private KPI symbolset. No kernel bundle is linked, packaged or signed.

A later [public service-timer stage](BUILD34-PUBLIC-SERVICE-TIMER.md) removes
that direct private import and passes static provider resolution. The refusal
below remains the evidence for this earlier checkpoint; neither stage is a
native kernel candidate or R3 hardware acceptance.

Only default `upstream34/vram-layout-fix`, PhxBringup build34 is in scope.
Build41/build42 remain withdrawn. Installed drivers, acceleration, desktop,
PR28 daily settings and recovery/monitoring policy are unchanged.

## Concrete complete-source defect and minimal correction

The preceding [owned service-timer stage](BUILD34-SERVICE-TIMER.md) passes its
CPU tests, but the complete translation unit fails on the actual SDK: the
service class uses `IOAccelPhxNativeClient *` before declaring the client type.
The CPU fixture already declared that type in its own class layout, so those
method-body tests could not detect this integration defect.

`tools/build34_exact_native_sdk.py` derives the unchanged preceding stage and
adds just `class IOAccelPhxNativeClient;` before `class PhxBringup`. It changes
no method, reader, mode, ABI, receipt or resource lifetime. Earlier transforms
remain frozen, and all 172 production inputs remain byte-identical. The
runner checks that removing exactly this declaration recovers its predecessor's
complete SHA256. It reproduces the missing-type error without the declaration.

## Actual compiler and input boundary

`tools/test_build34_exact_native_sdk.py` requires the accepted default branch,
the successful frozen timer evidence, a fresh ignored private output, native
Intel macOS and the independently reviewed MacKernelSDK checkout at commit
`3f750085caa17ec3a7880f11c11bf4f48cd6a164`. It reuses the existing SDK archive
validation: a clean independent checkout, exact Git object identities, 1,216
files with notices, and rejection of unexpected archive links or paths.

The runner freezes the complete real driver, the real native ABI/topology
headers, the staged ownership header, its four helper headers, prerequisite
recipes and SDK files. It compiles both untouched production and corrected
staged translation units with the existing x86_64 kernel C++17 flags, including
`-mkernel`, `-fapple-kext`, `-nostdinc`, no exceptions and no RTTI. No fake
IOKit classes, extracted-method adapter or host C++ standard library is used.
Every reported compiler dependency must resolve to the frozen source/SDK closure.
Sources, SDK/KDK inputs and compiler-tool hashes are checked again afterward.

The outputs are explicitly checked as x86_64 **MH_OBJECT**, a nonloadable
intermediate. The tool does not invoke a linker, the kext build recipe,
codesign, kmutil collection creation, an installer, a device opener or a GPU
probe. Private objects, SDK/KDK material and compiler output stay ignored.

The control retains its three existing field-shadow warnings. The staged
source has those same three warnings plus the already-unbound, unused
`exactFenceReader` field. These diagnostics are recorded and checked explicitly;
no warning suppression or production source change is introduced to hide them.

## Native timer provider refusal

The observed OS is macOS **26.7.2, build 25G332**. The supplied local KDK's
product-version/build metadata matches it. This is a metadata match, not proof
that a public XNU snapshot or SDK header is byte-identical to the running
kernel. The timer audit privately freezes the x86_64 Mach, Unsupported and
Private symbolsets, checks their bundle identifiers and hashes, then checks
only the real compiled object's timer imports against their exports.

| Staged timer import | Reviewed KDK provider |
| --- | --- |
| `_thread_call_allocate_with_options` | `com.apple.kpi.mach` |
| `_thread_call_enter` | `com.apple.kpi.mach` |
| `_thread_call_enter_delayed` | `com.apple.kpi.mach` |
| `_thread_call_free` | `com.apple.kpi.mach` |
| `_thread_call_cancel_wait` | `com.apple.kpi.private` only; admission refused |

The control already imports `_thread_call_cancel_wait`; the owned-timer stage
does not introduce this particular dependency. That inheritance is not an
exemption from native candidate admission. The earlier
[framebuffer timer work](BUILD34-VBL-SCHEDULING.md) also records a concrete
private-KPI collection-inclusion rejection. Do not add the private dependency,
weaken admission or treat a monolithic-kernel symbol as an available public KPI.
The next service-timer integration must use available public lifecycle APIs,
with actual cancellation, callback ownership and stop/rearm semantics checked.
The public IOKit timer/workloop pattern is a relevant existing local reference;
its framebuffer acceptance does not validate the service's own lifetimes.

The compiled control/staged objects have 375/376 undefined imports. Their
complete import delta is in the [sanitized evidence](validation/build34-r3-native-sdk-offline-20261121.json).
This audit does not claim full import resolution, successful collection
inclusion, module unload safety or an exact-mode capability/session contract.
It publishes symbol names, digests and scoped conclusions, not KDK binaries,
private paths, raw metadata or diagnostics.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-native-sdk \
  KERNEL_SDK="$KERNEL_SDK" KDK="$KDK" \
  EXACT_NATIVE_SDK_OUT=build/build34-r3-native-sdk-new-private
```

## Still required

No device reader is bound, permanent service/GPU quarantine remains, and the
native session/capability, independent global-prefix/visibility and paired
Mesa/CPU-fence protocol are unfinished. AMD notification, healthy service
reclamation, actual GPU correctness, desktop/FPS measurement and stated-duration
stability still need evidence in [the R3 ledger](BUILD34-R3-PLAN.md).
R4–R6 remain pending. Rollback consists of no longer deriving this declaration
stage; it requires no installed-system or power action.
