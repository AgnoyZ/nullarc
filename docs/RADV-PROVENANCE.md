# RADV-only artifact provenance and scope

## Authorization and reviewed boundary

On 2026-11-13 the owner authorized a manual public Actions artifact containing
only `libvulkan_radeon.dylib` and its corresponding sources, notices, provenance
and checksums, retained for seven days. The repository is public; this is a
public distribution. The separate two-kext exception and the full-stack upload
block remain unchanged. No release, installation, initialization, GPU test,
desktop takeover or reboot is authorized by this workflow.

The artifact is an experimental constructor-cleanup and allocation-diagnostic
candidate. It initializes destructor-owned state before fallible command-stream
creation, and records bounded native allocation refusals. It preserves failures;
their causes and desktop behavior remain unresolved.
The installed mixed userspace has incomplete source provenance. Do not claim
that a fresh build differs from the installed library only by this patch.

## Pinned source and notice review

The package verifies the actual inputs against `upstream.lock.json` and exports
committed source only. The review used the following exact revisions:

| Input | Commit | Review and packaged material |
|---|---|---|
| Mesa | `f5cb8ee032adabef599ae892ec4e42d796b84da9` | Complete base source, per-file notices, `docs/license.rst`, entire `licenses/` including exceptions |
| Cobalt64 | `d6c9aedf8e6526a39e349b5886cbc8c7ddf77f65` | Nine ordered Mesa patches, README, root MIT license, third-party notices and original ABI header |
| nullarc Phoenix series | `8aba872560a3c9b7dc7a0ddebfad001c6dddf315` | Seven ordered patches, README, original LICENSE/LICENSES and THIRD_PARTY_NOTICES |
| Vulkan-Headers | `6802bb4733b63ed5efd3adb308a6c885ef180ea1` | Complete committed source, LICENSE.md, Apache-2.0 and MIT texts |
| downstream nullarc | Package's exact source commit | Three ordered RADV patches, ABI/topology headers, build/verification/test recipes, project licenses and supplemental ABI notices |

Primary references: [Mesa licensing](https://docs.mesa3d.org/license.html),
[Cobalt patch license and ordering](https://github.com/Almosst-DEV/Cobalt64/blob/d6c9aedf8e6526a39e349b5886cbc8c7ddf77f65/mesa-patches/README.txt),
[Cobalt root license](https://github.com/Almosst-DEV/Cobalt64/blob/d6c9aedf8e6526a39e349b5886cbc8c7ddf77f65/LICENSE),
[Phoenix component license table](https://github.com/luuumi-dev/nullarc/blob/8aba872560a3c9b7dc7a0ddebfad001c6dddf315/LICENSE),
and [Vulkan-Headers license](https://github.com/KhronosGroup/Vulkan-Headers/blob/6802bb4733b63ed5efd3adb308a6c885ef180ea1/LICENSE.md).
The allocation diagnostic changes the MIT Darwin IOKit transport supplied by
the pinned Cobalt patch series. Its original SPDX notice is preserved in the
patch target and test fixture. No new runtime dependency beyond Apple system
logging is introduced. The existing compile/test workflow retains no artifact
by default; this diagnostic does not expand the publication exception.

The pinned Mesa licensing text and command-buffer source were read from a
Git-object-verified mirror at the identical commit; GitLab remains canonical.

Mesa is mostly MIT, with individual file terms; this review does not relicense
the whole source tree as MIT. The changed command-buffer source carries MIT
and its Red Hat, Bas Nieuwenhuizen and Intel attributions. Full source and all
license texts preserve the other source components' terms, even for components
not built. Cobalt's patch README explicitly releases its Mesa changes under
Mesa's license; the root MIT text is retained verbatim. The original Cobalt ABI
header has no overriding SPDX line, while the downstream PhxNativeABI.h
attributes layouts to BSD-3-Clause. Both the original MIT and supplemental BSD
notices are retained without resolving that attribution by relicensing it.
Phoenix patches are MIT under their pinned component table. Vulkan-Headers
uses Apache-2.0/MIT with its documented per-file exception; original source
headers and both texts are included. Root project license collections and
THIRD_PARTY_NOTICES remain intact; their descriptions of other components do
not imply that those components' binaries are included.

Only Mesa's AMD Vulkan driver is built: no Gallium/OpenGL/EGL/GBM, LLVM,
SPIRV-Tools or zstd runtime linkage, and Meson fallback downloads are disabled.
Actual linked dependencies must be Apple system libraries/frameworks only.
Apple SDKs, system libraries, build tools, kexts, Metal plugin, translator,
Vulkan loader, firmware, EFI, private configuration and raw diagnostics are
excluded. Bundled upstream source data/fixtures remain source material; no
other built runtime library is packaged.

## Package and verification

`radv-artifacts.yml` runs only by manual dispatch on the development branch
and `macos-15-intel`. `package_radv.py` requires clean pinned inputs, exact
ordered patch hashes (9 + 7 + 3), matching build report and no-device/ABI
evidence. Source-provenance JSON is compared structurally (object field order
is immaterial; patch array order and all values remain exact); license text
bytes are compared verbatim. It checks x86_64 Mach-O type 6, required exports,
relocatable dylib identity, system-only dependencies and strict ad-hoc signature verification
before and after staging. It rejects extra artifact files and symlinks.

The manual workflow's `retain_artifacts` input defaults to true, preserving the
reviewed seven-day RADV-only publication. Explicit false selects compile/test
validation and skips both package creation and upload. It still checks the
strict packaging policy on CPU and compiles/signs/tests the actual RADV. The
diagnostic investigation uses this false setting; no additional binary
publication or installation is implied.

The only runtime file is `libvulkan_radeon.dylib`. The package also carries
the build report and relocatable ICD JSON as metadata, complete Mesa and
Vulkan-Headers source archives, limited Cobalt/Phoenix/project source archives,
and a numbered patch series with hashes and origin commits. Source exports
reject traversal, hard links and special files; relative source symlinks must
stay within the component root. Archives normalize ownership and timestamps.
An inner manifest covers every file; an outer SHA256SUMS covers the tarball.
Only that tarball and its checksum file are uploaded, for seven days.

Reconstruction: unpack `SOURCE/mesa-base.tar.gz`; apply the nineteen patches
listed in `SOURCE/patch-series.json` in order using `git apply` (or `patch -p1`)
from the Mesa root. Unpack the project, Cobalt, Phoenix and Vulkan source
archives to inspect original notices and reproduce the build recipe. The
source archives contain no Git history: to run the unmodified preparation
script, obtain clean checkouts at the recorded commits, including full nullarc
history, then use the arguments in the packaged workflow. See
`tools/radv-build-requirements.txt` and `tools/build_radv.py` for build options.

CPU constructor fault injection and four hosted no-device refusal cases are
source/ABI/packaging checks. They establish no target GPU execution or desktop
acceptance. No-device probes refuse target services and must not be run on the
laptop as a GPU test. Downloaded packages are staged only. A later deployment
requires its own route and rollback review; do not overwrite a mapped library.
The historical preparation record retains its pre-authorization observations.
