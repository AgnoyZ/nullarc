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
GPU, authorize a hardware scope or supply a full RADV dylib.

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
