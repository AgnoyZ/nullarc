# Original34 RADV submission experiment

This is a separately scoped, active source recipe for default branch
`upstream34/vram-layout-fix`. It does not make the historical `patches/`
directory an apply list. It contains no kernel, firmware or runtime binary.

`0003-radv-exact-completion-bookkeeping.patch`, the dependent
`0004-radv-exact-multitarget-wait-query.patch` and then
`0005-radv-exact-cs-dependency-guard.patch` are **separate R3 source-only
prerequisites**, not patches automatically applied by the runtime/tail
recipes below. The dedicated CPU runners test the pinned sync provider;
0004 follows 0003 and also changes its internal userspace backend header.
The new capability defaults false and no production initializer enables it.
0005 additionally changes the CS wrapper: exact mode waits for payload
completion on the CPU before a consumer submit and refuses unsupported
nonempty legacy dependency chunks. Legacy behavior remains unchanged. None
of these patches implements or enables an exact native backend, native GPU
queue dependencies or a deployment. See
[R3 design, CPU evidence and remaining admission work](../docs/BUILD34-EXACT-COMPLETION.md).

`0001-radv-original34-immutable-ib-tail.patch` modifies exactly three MIT Mesa
Darwin transport files. The input hashes and the 30-file build/test dependency
closure are pinned by `tools/upstream34_layout/radv_ib_tail_sources.json`.
See [the design, provenance and acceptance limits](../docs/BUILD34-RADV-IB-TAIL.md).

The explicit environment setting `RADV_DARWIN_BUILD34_IB_TAIL=1` enables the
compute-only experiment when a new Mesa shared core is created. It is disabled
by default and refused for WindowServer. Do not set it globally or use it to
start a desktop. This recipe does not install or load anything, initialize a
GPU or authorize a hardware scope. The original staging/probe recipe does not
supply a full RADV dylib; the separate compile-only runtime recipe below does.

To stage the patch from an independently verified matching Mesa source tree:

```sh
python3 tools/upstream34_layout/radv_ib_tail.py \
  --mesa-source /path/to/verified/mesa --out build/radv-tail-source-private
```

Add `--compile-probe` with a fresh output path to freeze the complete dependency
closure and compile/sign the x86_64 native probe. Compilation never executes
the resulting binary, including with `--check` or invalid arguments. The
native probe links the actual Mesa core, VA allocator, sync provider and CS
marshaller. It replaces only the platform open/map/call boundary to enforce
one direct PCI-verified client, without proxy fallback or open retries.

Run CPU verification separately:

```sh
python3 tools/test_build34_radv_ib_tail.py \
  --mesa-source /path/to/verified/mesa --out build/radv-tail-host-private
```

All CPU executions use fake platform ops. The native probe still requires a
fresh separately pinned, independently recoverable hardware scope for each
policy; neither recipe arms one. Build41/build42 are rejected, not candidates.

## Full runtime compilation and CPU load check

`tools/upstream34_layout/radv_ib_tail_runtime.py` accepts the **complete** Mesa
baseline after the same 19 reviewed patches, including archived symlinks. It
checks the full 12,969-file/link inventory against
`tools/upstream34_layout/radv_ib_tail_runtime_sources.json`, stages the existing
three-file patch and requires its output to match the hardware-tested sources.
It then applies `0002-radv-original34-tail-enumeration-owner.patch` to the
separately pinned MIT `radv_physical_device.c`. Only exact opt-in value `1`
retains a core owner across physical-device enumeration and subsequent device
creation. The physical device's existing destructor releases that owner.
Default/`0` enumeration remains unchanged. This fourth file has separate CPU
and runtime-build evidence; it is not covered by the earlier transport GPU test.
It never applies the historical kernel patches or builds a kernel.

Use native x86_64 macOS and Python 3.10 or later. Prepare an isolated Python
environment with Meson 1.9.1, Ninja 1.13.0, Mako 1.3.10, MarkupSafe 3.0.3,
PyYAML 6.0.3 and packaging 25.0. Provide glslang 16.5.0 and pkg-config in the
explicit tool directories. The manifest records glslang's immutable source
commit/archive hash; it is a build tool, not a runtime component. CMake 3.31.6
can compile it privately with external dependencies, SPIR-V optimization,
HLSL, precompiled headers, tests and installation disabled. No dependency is
installed automatically by this recipe.

```sh
nice -n 15 taskpolicy -b /path/to/venv/bin/python \
  tools/upstream34_layout/radv_ib_tail_runtime.py \
  --mesa-source /path/to/complete/verified/mesa \
  --out build/radv-tail-runtime-private \
  --toolchain-bin /path/to/venv/bin \
  --toolchain-bin /path/to/glslang/bin \
  --toolchain-bin /path/to/pkg-config/bin
```

Each attempt needs a fresh output. Meson uses `--wrap-mode=nofallback` and
Ninja compiles only the RADV dylib target with `-j1`. The recipe verifies
Mach-O x86_64/dylib identity, system-only runtime dependencies, required
exports, the actual compiled transport/header dependencies and their presence
in the dylib link closure, including the fourth enumeration source and its
Darwin DRM header. It signs the output and performs an export/service
policy load check with physical-device enumeration disabled.

The load check uses a separate IOKit interposer dylib. Before loading its
target, it tests the open blocker with a null service and requires the expected
blocked call; an unavailable guard stops before target loading. The counter is
then reset and must remain zero throughout target load, export/service checks
and unload. This checks linking and CPU-only loading, not Vulkan execution.

Test all seven blocked API entrypoints, a benign library and a missing export
using only CPU fixtures and null/invalid IOKit handles:

```sh
python3 tools/test_build34_radv_runtime_smoke.py \
  --out build/radv-tail-runtime-smoke-tests-private
```

Test the actual baseline/patched enumeration function, actual DRM wrapper
functions and real shared core/VA allocator with CPU platform fixtures:

```sh
python3 -B -I tools/test_build34_radv_enumeration_owner.py \
  --mesa-source /path/to/complete/verified/mesa \
  --transport-source /path/to/staged/source/src/amd/common/darwin \
  --out build/radv-tail-enumeration-owner-cpu-private
```

The runner verifies all 30 transport dependencies, the wrapper and fourth-file
hashes, the unchanged hardware-tested transport outputs, and the protected
original34 source. Its physical-device constructor is a CPU fixture with real
core acquisition/release, not full Vulkan execution. It explicitly records the
baseline's existing orphaned profile sync clone; this patch does not fix it.

After a successful complete build, exercise its actual Vulkan enumeration,
dedicated-compute logical-device creation and destruction with a separate CPU
IOKit fixture:

```sh
python3 -B -I tools/test_build34_radv_runtime_enumeration.py \
  --runtime build/radv-tail-runtime-private \
  --out build/radv-tail-runtime-enumeration-cpu-private
```

The fixture audits every runtime IOKit import, tests its dependent-dylib open
interposition before loading RADV, and implements only fake setup/teardown in
CPU memory. Its only real IOKit helper constructs a matching dictionary.
Native submit/wait selectors and all unexpected calls are rejected. This tests
the full Vulkan CPU lifecycle, not GPU execution or shader correctness.

Results, logs, the source snapshot and the dylib stay in ignored `build/`.
Successful compilation does not install the library, select it for an
application, enable the opt-in policy or authorize a GPU scope. The existing
bounded probe comparison is separate from any future full-runtime hardware
acceptance. No binary artifact is uploaded by these commands.

## Complete-runtime probe preparation

Prepare the separate native probe/guard from the verified four-file runtime:

```sh
nice -n 15 taskpolicy -b python3 -B -I \
  tools/upstream34_layout/radv_ib_tail_runtime_probe.py \
  --runtime build/radv-tail-runtime-private \
  --out build/radv-tail-complete-probe-private \
  --glslang /path/to/pinned/glslangValidator
```

This compiles/signs the probe and dependent guard, freezes the private runtime,
and executes only the no-client interposition/forwarding self-test. It never
invokes GPU mode. CPU-only fault tests require separate fresh outputs:

```sh
nice -n 15 taskpolicy -b python3 -B -I tools/test_build34_radv_runtime_probe.py \
  --runtime build/radv-tail-runtime-private \
  --out build/radv-tail-complete-probe-cpu-private \
  --glslang /path/to/pinned/glslangValidator
nice -n 15 taskpolicy -b python3 -B -I tools/test_build34_radv_runtime_guard.py \
  --cpu-probe build/radv-tail-complete-probe-cpu-private/compiled \
  --runtime build/radv-tail-runtime-private \
  --out build/radv-tail-complete-guard-cpu-private
```

The [scope and evidence limits](../docs/BUILD34-RADV-RUNTIME-PROBE.md) remain
mandatory. CPU binaries are explicitly identified and cannot admit a hardware
scope. Real execution needs a fresh independent recovery/deadline packet; no
launcher, installation or automatic GPU retry is part of these commands.

The subsequent [bounded complete-runtime hardware result](../docs/BUILD34-RADV-RUNTIME-PROBE.md#complete-runtime-hardware-result)
passed two whole-arena compute dispatches with actual changed bytes at the
same IB address, then independently recovered and retired. This verifies the
explicit opt-in compute workaround only; it does not enable the default policy,
install a runtime, fix the unchanged kernel's single-IB path or accept graphics,
desktop or FPS behavior.
