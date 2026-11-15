# Reproduce the original build-34 VRAM layout correction

The default branch `upstream34/vram-layout-fix` contains the correction directly
in `tools/phxctl/`. The entire `src/` tree remains upstream v0.4.0-alpha commit
`9dd76b604fca5e0125bd3caa5723df0f611ff27f`, including the build-34 kernel.
The separate downstream development branch is not the source baseline here.

```sh
make test
make test-upstream34-layout
python3 tools/upstream34_layout/build.py build/upstream34-layout-example-private --compile
```

The focused tests require macOS Command Line Tools. They compile the actual
checked-in C entrypoints under ASan/UBSan, replace all IOKit calls, and use fake
shell commands. No live GPU, sudo, shutdown or driver installation is invoked.

The recipe requires a nonexistent output directory. It materializes six pinned
upstream user-space inputs, applies `layout-fix.patch`, and copies the canonical
`tools/phxctl/PhxUpstream34Layout.h`. It refuses any difference between those
seven generated files and the actual checked-in helper sources. Keep the patch
and checked-in sources synchronized when changing this narrow correction.

On macOS, `--compile` compiles and ad-hoc signs only `mesboot` and `phxctl` as
x86_64 executables. It verifies their signatures and architecture, and records
hashes with private compiler logs. It does not install or run either executable,
build a kernel, download firmware or publish binaries. The original unused
`val` warning remains unchanged.

See [scope, evidence and rollback](../../docs/UPSTREAM34-LAYOUT-CORRECTION.md).
CPU tests and successful compilation do not prove hardware acceleration,
an accelerated desktop or ownership of the selected VRAM regions.
