> **默认分支 `upstream34/vram-layout-fix`：build 34 基线＋显存地址修复＋A1/A2/修正版 A3。**
> 2026-11-16 已将 `backport/upstream34-a1-a3` 的既有提交与实机验证记录迁入，
> 包含 A3 的 2 秒采样修正；按所有者要求，迁入操作不再重复测试。
> 2026-11-17 在原版与等长 NOP 对照均复现 IB 错值后，外层 ACQUIRE 镜像通过两次受保护提交，
> 已将逐字节相同的最小计算提交同步修改纳入默认源码；内核 ABI、启动工具及 A1/A2/A3 保留。
> 实机测试结束已恢复原版 build34、GPU 停用；源码集成不代表本机持续运行修复镜像。
> 2026-11-17 修复镜像配合原已安装运行库通过约 151 秒桌面接管、Metal 输出与帧进展验证，随后独立恢复。
> **2026-11-16 的 WindowServer watchdog 仍保留；持续使用加速桌面的准入继续 HOLD。**
> 新增验证不代表长期稳定、卡顿根因已解决、PR28 等待已实测或帧率提高。
> [桌面接管短测、观察器修正与恢复](docs/BUILD34-DESKTOP-VALIDATION.md) ·
> [计算提交同步修改、三组对照与恢复记录](docs/BUILD34-SUBMIT-MEMSYNC.md) ·
> [回移内容、既有验证与回退](docs/UPSTREAM34-BACKPORT.md) ·
> [原始显存修复基线](docs/UPSTREAM34-LAYOUT-CORRECTION.md)。
> 以下上游参考机器的表现不代表本机长期稳定性或本次迁入的帧率结果。
>
> **Default: build-34 baseline, VRAM layout correction and A1/A2/corrected A3.**
> The existing candidate commits and hardware records are preserved. No repeat
> testing is required for this source transfer. Native accelerated desktop
> adoption remains on HOLD after the post-gate WindowServer watchdog.
> Active development and hardware tests use default build34 only. The minimal
> compute-submit ACQUIRE fix passed two guarded native dispatches after both
> original and equal-footprint NOP controls failed, and its exact source is
> integrated. A subsequent bounded desktop/Metal trial passed with the retained
> installed runtime, including about 151 seconds of frame observation. The
> machine was recovered to the original image with GPU off. Persistent desktop
> adoption, long-run stability, PR28 GPU waits and FPS remain unaccepted.
> This branch publishes no binaries.

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/brand/nullarc-logo-dark.svg">
    <img src="assets/brand/nullarc-logo-light.svg" alt="nullarc" width="420">
  </picture>
</p>

<p align="center">
  <b>Metal on AMD Radeon 780M (soon also Radeon 740M and 760M) for macOS Tahoe.</b><br>
  GPU bring-up, a display driver WindowServer composites on, and Metal over Vulkan (Mesa RADV)<br>
  for Phoenix / Hawk Point APUs (RDNA 3, GC 11.0.1, gfx1103).
</p>

<p align="center">
  <img alt="macOS Tahoe 26" src="https://img.shields.io/badge/macOS-Tahoe%2026-0B0D12?logo=apple&logoColor=white">
  <img alt="Radeon 780M gfx1103" src="https://img.shields.io/badge/GPU-Radeon%20780M%20%C2%B7%20gfx1103-FF3D2E?logo=amd&logoColor=white">
  <img alt="Metal over Vulkan" src="https://img.shields.io/badge/Metal-over%20Vulkan%20(RADV)-7C5CFF">
  <a href="https://github.com/luuumi-dev/nullarc/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/luuumi-dev/nullarc/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-multi-FF2D87"></a>
</p>

<p align="center"><b>English</b> · <a href="README_RU.md">Русский</a></p>

---

## Status

Measured on the reference machine — Firebat U6C, Ryzen 7 H 255, Radeon 780M, 2560×1600 120 Hz eDP, macOS Tahoe 26.6.2 —
in October 2026:

| | |
|---|---|
| **Desktop** | WindowServer composites on the 780M at the panel's 120 Hz. CoreAnimation runs at 119–120 fps; dragging a window, 116 fps. |
| **Liquid Glass** | Dock, widgets, Control Center and in-app glass are drawn by the GPU with Apple's own compositor shaders (translated). |
| **Metal in apps** | Every process gets the Metal device, sandboxed WebKit GPU processes included. About 46 apps checked with no crashes, Safari, Chess and Spotify among them. |
| **Display sleep / wake** | Works. |
| **First use of a new effect** | A one-time pause of about 1–3 s while its shader is translated and compiled. After that it comes from the disk cache. |
| **Not yet** | External displays (HDMI, USB-C), hardware video decode/encode, backlight control. |

Other Radeon 780M / 760M machines (Phoenix, Hawk Point) are untested.

Known bugs and gaps, ranked by severity, are tracked in [BUGS.md](BUGS.md) (in Russian).

## How it works

```mermaid
flowchart TD
  apps["Apps · WindowServer"] -->|Metal| plugin["NVMTLDriver.bundle<br/>Metal objects on Vulkan"]
  plugin -->|"AIR → SPIR-V"| xlate["libnvmtl_translate"]
  plugin -->|Vulkan| radv["Mesa RADV<br/>libvulkan_radeon.dylib"]
  plugin -->|IOAccelerator| accel["PhxAccel.kext<br/>NMXAccel · PhxAMDFB · PhxAGDC"]
  radv -->|"IOKit user client"| bringup["PhxBringup.kext<br/>PSP · MES · GPUVM"]
  bringup --> gpu[("Radeon 780M")]
  accel -->|scan-out| panel["eDP panel · DCN 3.1.4"]
```

| Component | Installed in | Source | Role |
|---|---|---|---|
| `PhxBringup.kext` | OpenCore `EFI/OC/Kexts` | [`src/phxbringup`](src/phxbringup) | Loads firmware through the PSP, powers up GFX (SMU/IMU), starts the MES scheduler and the compute and graphics queues, gives every process its own GPUVM address space, implements the BO/submit ABI RADV uses. |
| `PhxAccel.kext` | Auxiliary kernel collection | [`src/phxaccel`](src/phxaccel) | `NMXAccel` IOAccelerator, the `PhxAMDFB` framebuffer (VRAM pool, 120 Hz vblank, frame copy to scan-out) and `PhxAGDC` display control. |
| `NVMTLDriver.bundle` | `/System/Library/CoreServices/CoreTypes.bundle/Contents/Library/PhxGPU`, linked from `/Library/GPUBundles` | [`src/nmplugin`](src/nmplugin) | The Metal driver plugin: Metal on Vulkan, zero-copy IOSurfaces, shader caches. |
| `libvulkan_radeon.dylib` | `PhxGPU/nvmtl` | Mesa + [`mesa-patches-phoenix`](mesa-patches-phoenix) | RADV for gfx1103 with a Darwin winsys. |
| `phxboot` | LaunchDaemon `local.phxboot` | [`tools/phxctl/phxboot.sh`](tools/phxctl/phxboot.sh) | Brings the GPU up at boot before WindowServer opens the panel, with fail-safes that fall back to the firmware framebuffer. |

`libnvmtl_translate.dylib` (Metal AIR → SPIR-V, LGPL-3.0, based on metal2vulkan) ships prebuilt with NullMoth's
plugin; its source is attached to every release. The `NVMTL` prefix is NullMoth's too: none of this is an NVIDIA driver.

## Installing

Download `nullarc-<version>.zip` from the [releases page](https://github.com/luuumi-dev/nullarc/releases) and follow
**[docs/INSTALL.md](docs/INSTALL.md)**. In short: add `PhxBringup.kext` and the boot-args to OpenCore, reboot, run
`sudo ./install.sh --windowserver` from the release folder, reboot twice.

> [!WARNING]
> WindowServer only loads an ad-hoc signed driver with AMFI relaxed (`amfi=0x80`, `amfi_get_out_of_my_way=0x1`).
> That turns library validation off system-wide and FairPlay playback (Apple TV+, Netflix in Safari) stops working.
> `uninstall.sh` and the guide's last section undo everything.

## Building

On the Mac (Command Line Tools, [MacKernelSDK](https://github.com/acidanthera/MacKernelSDK)):

```sh
sh src/phxbringup/build.sh /path/to/MacKernelSDK      # PhxBringup.kext
sh src/phxaccel/build.sh /path/to/MacKernelSDK        # PhxAccel.kext
```

The plugin builds from `src/nmplugin/NVMTLDevice.m`, which includes the rest of `src/nmplugin`. RADV: Mesa
`f5cb8ee0` + Cobalt64's Darwin patches + [`mesa-patches-phoenix`](mesa-patches-phoenix/README.txt).

Unit tests (firmware parsing, IP discovery) run on Linux or macOS and in CI:

```sh
make fixtures   # Phoenix firmware from linux-firmware
make test
```

## Notable fixes

- **Zero-copy IOSurfaces** — textures are linear images over the surface's own pages; WindowServer CPU 77 % → 36 %.
- **Surface keep cache** — CoreAnimation re-wraps the same IOSurfaces every frame; keeping their imports took a dragged window from 64–69 to 116 fps.
- **VRAM pool** — per-allocation contiguous memory fragmented after hours and display wake froze; one 512 MB pool now.
- **RADV mutable descriptor lists** — indexed by the sorted binding order instead of the original one; broke CoreImage blurs and Tahoe's layered icons.
- **Nested loop unrolling (Mesa 0006)** — a new compositor shader variant compiled ~2 s in RADV, one loop level per optimisation round; now ~1 s with identical code.

## The name

**null + arc**: the empty-set sign of a driver that did not exist, its ring opened into an arc.
See the [brand guide](assets/brand/README.md).

## License and credits

Several licenses apply; see [LICENSE](LICENSE), [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [LICENSES/](LICENSES).

- Code written for nullarc (`src/phxbringup`, `tools/phxctl`, …): MIT, or GPL-2.0-only at your option.
- `src/phxaccel`, `src/nmplugin`, `tools/nvmtl-patches`: derived from NullMoth's macOS driver, **PolyForm Noncommercial 1.0.0** — no commercial use.
- `mesa-patches-phoenix`: MIT, as Mesa. Release packages also carry LGPL-3.0 (shader translator), LLVM and AMD firmware; see the notices.

Built on the work of the Linux `amdgpu` team, Mesa, NullMoth, [Cobalt64](https://cobalt64.com),
[Acidanthera](https://github.com/acidanthera) and the AMD-OSX community.
