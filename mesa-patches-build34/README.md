# Original34 RADV submission experiment

This is a separately scoped, active source recipe for default branch
`upstream34/vram-layout-fix`. It does not make the historical `patches/`
directory an apply list. It contains no kernel, firmware or runtime binary.

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
in the dylib link closure. It signs the output and performs an export/service
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

Results, logs, the source snapshot and the dylib stay in ignored `build/`.
Successful compilation does not install the library, select it for an
application, enable the opt-in policy or authorize a GPU scope. The existing
bounded probe comparison is separate from any future full-runtime hardware
acceptance. No binary artifact is uploaded by these commands.
