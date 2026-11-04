# Downstream 780M work (branch `downstream/780m-tahoe`)

This branch is the Radeon 780M / Phoenix (gfx1103, PCI `1002:1900`) research work applied on top of
upstream `luuumi-dev/nullarc` at `cbb08dd` (2026-10-21). Upstream `main` is kept untouched in this fork so
it can be re-synced; all downstream commits live only on this branch.

It is a hardening/precision pass over the upstream bring-up and display paths, not a new driver and not a
hardware-validated release. Nothing here has been executed on the target laptop.

Since 2026-11-02 this fork is the only working repository: the staging/build/test tooling, CI workflow,
validation evidence and research documents that used to live in `AgnoyZ/radeon-780m-tahoe` moved here
(see `docs/MIGRATION.md`).

## What the branch adds

- Shared, testable policy and layout headers used by the patched sources:
  `src/phxbringup/{PhxHardwarePolicy.hpp, PhxPspLayout.h, PhxBootMemory.h, PhxGartLayout.h,
  PhxMesQueueLayout.h, PhxFirmwareProfile.h}`,
  `src/phxaccel/{PhxHardwarePolicy.hpp, PhxPresentPacing.hpp, PhxCopyPath.hpp}`, `src/nmplugin/PhxRuntimePath.h`.
  `PhxFirmwareProfile.h` is metadata only, generated from a separately reviewed firmware lock; it
  contains no firmware bytes. `PhxPresentPacing.hpp` holds the display path's present-completion, gap-bucket
  and copy-hold rules as pure functions, asserted by `tests/test_present_pacing.cpp`; `PhxCopyPath.hpp` holds
  its row-path selection and ARGB2101010 → XRGB8888 narrowing, asserted by `tests/test_copy_path.cpp`.
- 28 downstream commits, in order:

| # | Commit subject | Area |
| --- | --- | --- |
| 0001 | strict hardware execution | device gate, no fabricated retirement |
| 0002 | plugin-relative RADV | plugin loader path |
| 0003 | bring-up aperture bounds | overflow-safe range checks |
| 0004 | checked bring-up transport | every IOKit call and reply length |
| 0005 | checked GPU completion | terminal completion before later writes |
| 0006 | bounded MES submission | frame/ring bounds |
| 0007 | checked PSP completion | PSP/TMR lifecycle |
| 0008 | checked firmware control | snapshot authentication |
| 0009 | explicit PSP layout | shared layout descriptor |
| 0010 | checked TOC initialisation | TOC response drives TMR size |
| 0011 | profile firmware sequence | nine-file firmware sequence |
| 0012 | checked GFX power sequence | SMU/IMU power handshake |
| 0013 | explicit GART bootstrap | derived MC/physical addresses |
| 0014 | profile MES start | scheduler/KIQ entrypoints |
| 0015 | explicit scheduler queue | MQD/HQD and completions |
| 0016 | explicit compute ring probe | checked arena and doorbells |
| 0017 | checked queue adoption | aliasing and offset checks |
| 0018 | checked VMID binding | context/root/slot ownership |
| 0019 | deferred client context retirement | ownership transfer |
| 0020 | deferred BO release and checked unmap | retirement semantics |
| 0021 | serialized queue retirement | completion snapshots |
| 0022 | checked page-table backing | allocation and walk checks |
| 0023 | checked walk cleanup | map/unmap rollback |
| 0024 | checked context-table clear | cached backing |
| 0025 | GFX11 shader dispatch probe | 79-word licensed shader |
| 0026 | share GFX11 dispatch packets | shared packet builder |
| 0027 | bounded IB debug reads | executable/mapping/BO bounds |
| 0028 | checked framebuffer pool and alias retry | display path |

- `tools/phx_boot_gate.sh`: an ordered, fail-safe stage runner for bring-up. It requires
  `--expected-build`, refuses non-Darwin/non-x86_64 hosts, runs an operator-supplied stage directory
  with per-stage timeouts, stops at the first failure, always runs the operator-supplied release hook
  after taking the lock, keeps a crash marker (a killed attempt makes the next run refuse), and never
  reboots, writes NVRAM, writes sysctl, kills by process name, installs anything, or embeds an address.
  It ships no stages and no installer.
- Phase-1 display measurement that CI can keep honest while the target laptop is unavailable:
  `tools/phx_baseline.sh` (read-only capture of the display counters, including the present cadence),
  `tools/phx_baseline_report.py` (turns that capture into the H1–H4 verdict against the thresholds in
  `docs/analysis.md` §9) and `tools/phx_counter_contract.py` (fails when the capture, the kernel sources
  and the analysis stop naming the same OIDs or a knob default moves). `docs/CI-WITHOUT-HARDWARE.md`
  states what this establishes and what it explicitly does not.
- `tools/phx_install_plan.py`: the OpenCore part of an install, written as numbered operator steps plus the
  rollback, with no apply mode. It reads an existing `config.plist`, checks the bundles and their digests, and
  refuses a system location, a foreign kext or a mismatched build. It stops where upstream's AMFI/CSR changes
  begin and lists them as the owner's decision, because this repository does not weaken OS security or write
  system locations (`docs/INSTALL-PLAN.md`).

## Behaviour changes to be aware of

- The kernel components start only with `phx780m=1`, on Darwin 25 and PCI `1002:1900`. Without the boot
  argument they decline to start.
- No synthetic fence retirement: a submit/wait that has no hardware behind it returns `kIOReturnNotReady`
  instead of reporting success.
- Graphics packets are no longer silently run on the compute queue (or vice versa).
- The downstream `mesboot`/`phxctl` paths are stricter than upstream's scripts and will refuse layouts or
  replies upstream accepted.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/` | Driver sources plus the canonical downstream headers and `src/README.md` |
| `tools/` | Staging, build, firmware manifest, target inventory/preflight and boot-gate tooling |
| `tests/` | Python suite, C++ sanitizer harnesses, fake-IOKit runners and shell fixtures |
| `docs/` | Design notes, audit records, migration notes and `docs/validation/` evidence |
| `docs/SUPPORT-STATUS.md` | Per-area table of what this branch can claim today and what needs the target laptop |
| `patches/` | Historical record of the 28-commit series; hashed by staging, never applied |
| `.github/workflows/build.yml` | Source tests on Linux and the macOS kext/plugin/RADV/LLVM build |

## Building and testing

Same prerequisites as upstream for the kexts: an Intel Mac with Command Line Tools and MacKernelSDK. The
sources keep upstream's build scripts and identifiers. The full pipeline (including Mesa RADV, LLVM and the
translator) is described in `docs/BUILD.md` and runs in CI.

```sh
python tools/prepare_source.py build/review-source     # exports HEAD, records provenance
python -m unittest discover -s tests -v                # source/staging/runner tests
clang++ -std=c++17 -Wall -Wextra -Werror -fsanitize=address,undefined -Isrc tests/test_hardware_policy.cpp -o build/test-policy
```

```sh
sh src/phxbringup/build.sh /path/to/MacKernelSDK
sh src/phxaccel/build.sh /path/to/MacKernelSDK
```

The boot gate is used without installing anything:

```sh
sh tools/phx_boot_gate.sh --check --stages /path/to/reviewed-stages --expected-build 32
sh tools/phx_boot_gate.sh --state /private/var/phxgate --stages /path/to/reviewed-stages \
    --expected-build 32 --release /path/to/release-hold.sh --timeout 60
```

## Licensing and provenance

Upstream files keep their original licences: `src/phxbringup` and `tools/phxctl` are MIT or GPL-2.0-only
at your option, while `src/phxaccel` and `src/nmplugin` derive from NullMoth and are PolyForm
Noncommercial 1.0.0. See `LICENSE`, `THIRD_PARTY_NOTICES.md` and `LICENSES/`. No firmware, kext build
output or Apple component is included. The added headers and `tools/phx_boot_gate.sh` are original
downstream work offered for noncommercial research use alongside this branch; this branch does not
grant any additional redistribution rights over upstream components.

## Syncing with upstream

```sh
git remote add upstream https://github.com/luuumi-dev/nullarc.git   # once
git fetch upstream
git rebase upstream/main
```

The commits are intentionally one-per-change so a rebase that drops a now-upstream fix is easy to spot.
