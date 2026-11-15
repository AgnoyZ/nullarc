# Original build-34 layout correction

This is an isolated recipe for upstream v0.4.0-alpha commit
`9dd76b604fca5e0125bd3caa5723df0f611ff27f`. It does not build the downstream
build-39 kernel, relabel a kernel, install files or execute GPU commands.

```sh
python3 tools/upstream34_layout/build.py build/upstream34-layout-example-private --compile
make test-upstream34-layout
```

The output directory must not exist. The recipe materializes six pinned
upstream user-space inputs and their applicable notices, applies the single
scoped patch, and copies the shared layout validator. On macOS, `--compile`
builds and ad-hoc signs only `mesboot` and `phxctl`, recording input/output
hashes and retaining compiler logs. An existing upstream unused-variable
warning is preserved. No firmware, plugin, accelerator, runtime or EFI is
downloaded, copied into this repository or published.

The separate operational candidate uses the retained, unchanged original
build-34 kext. Source arithmetic and fake-IOKit/shell checks are not GPU
execution or memory-ownership evidence. See
[the correction record](../../docs/UPSTREAM34-LAYOUT-CORRECTION.md) before
considering any deployment. The existing downstream sources and `main` are
not replaced by this recipe; `patches/` remains historical.
