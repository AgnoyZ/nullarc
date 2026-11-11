# 原生 2× HiDPI 候选路径

2026-11-11：参考 NullMoth NVIDIA 项目的 HiDPI 模式标志和像素/逻辑尺寸分离，
为实际显示路径 `src/phxaccel/accel/phxfb.cpp`（`PhxAMDFB`）增加默认关闭的
`phxfbhires=1`。本文件描述的是**待目标机验证的实现**，不是显示成功或加速成功的报告。
当前没有 Tahoe 目标机的 OS build 或 HiDPI 实机结果，也没有安装、部署或修改 EFI。

## 支持范围

| 项目 | 本次实现 |
| --- | --- |
| 原生 2× | 例如固件已经输出 2560×1600，候选桌面为逻辑 1280×800，backing pixels 仍为 2560×1600 |
| 驱动开关 | 只有 `phxfbhires=1` 且尺寸、32 位 pitch 合法时，原有模式才增加 `kDisplayModeNativeFlag` / `kDisplayModeValidForHiResFlag` |
| 显示覆盖文件 | 离线生成仅包含原生像素尺寸的 `scale-resolutions`，需要操作者单独审核 |
| 只读探针 | 列出 CoreGraphics 的当前/可选模式、逻辑尺寸、backing pixels、刷新率与宿主 OS 版本/build |
| 任意“看起来像”尺寸 | 未实现：例如 2560×1600 面板的逻辑 1920×1200 需要 3840×2400 渲染后缩小 |
| 硬件模式、刷新率、缩放器 | 未修改；仍只有固件点亮的一个模式，不写显示引擎，不声明 up/downsample 能力 |

`getInformationForDisplayMode()` 的 nominal 尺寸与 `getPixelInformation()` 的 active
尺寸都保持**物理像素**。不能把它们直接改成一半：加速器的 CPU present 路径要求
源图宽高恰好等于 scan-out 宽高，尺寸不同会拒绝。HiDPI 的半尺寸逻辑坐标应由
CoreDisplay/WindowServer 建立；标志与覆盖文件是否足以让 Tahoe 选择它，仍需实测。
这不是新增 GPU 合成或缩放路径，也不代表桌面 FPS 或 Metal 加速得到验证。

## 参考与许可证审阅

本次固定参考：`nullmoth/nvidia-macos-driver` 提交
`7412cdde81447f78da0ebb64216dc258d8beaedb`（2026-11-11 审阅）。

- `kexts/NVRMFB/fb/nvrm-fb.cpp` 的 `getInformationForDisplayMode()` 为 scaled 模式
  设置 `kDisplayModeValidForHiResFlag`；`getPixelInformation()` 报告实际 backing pixels。
- 该项目 `computeScanoutCaps()` 的 `nvfbhidpi=1` 会预留更大的渲染面，
  `publishTimingCaps()` 声明 NVIDIA 硬件缩放能力。本 AMD 固件帧缓冲没有等价实现，
  因而没有移植这些能力、参数或硬件代码。该文件的 20 字节旋转模式记录也不是本次格式。
- 参考提交根 `LICENSE` 为 PolyForm Noncommercial 1.0.0，要求
  `Copyright (c) 2026 NullMoth Systems (https://nullmothsystems.com)`。已阅读根 `NOTICE`：
  Mesa、翻译器、NVIDIA 内核接口和固件各有不同许可；根许可不能替代组件许可审计。
- 本次没有从参考项目复制代码、二进制、固件或安装流程；`src/phxaccel` 及新增头文件
  保持该组件原有 PolyForm 许可。本仓库 `LICENSE`、`LICENSES/`、
  `THIRD_PARTY_NOTICES.md` 保持完整。公开 CI 不上传实验二进制。

IOGraphics 类型以固定 MacKernelSDK 提交
`3f750085caa17ec3a7880f11c11bf4f48cd6a164` 为准：HiRes flag 为 `0x00800000`，
Native flag 为 `0x02000000`；display vendor/product ID 都是 UInt32。
12 字节 `scale-resolutions` 记录使用三个大端 UInt32：原生宽、原生高、HiDPI 标记 1。
2560×1600 的记录是 `00000a000000064000000001`，不是逻辑 1280×800。
常见覆盖文件的该格式另与 `xzhih/one-key-hidpi` 脚本交叉核对；没有采用该脚本的
EDID 改写、系统安装或安全设置步骤。

## 构建与离线生成

源码构建沿用 `BUILD.md` 的 Intel macOS / MacKernelSDK 配方。独立校验：

```sh
python3 -m unittest discover -s tests -p 'test_hidpi_tools.py' -v
python3 tools/test_hidpi.py
xcrun clang -arch x86_64 -fobjc-arc -Wall -Wextra -Werror \
  tools/phx_hidpi_probe.m -framework Foundation -framework CoreGraphics \
  -o build/phx-hidpi-probe
```

探针无需 root，不设置模式，不读取 EDID、序列号或 UUID：

```sh
build/phx-hidpi-probe > build/hidpi-before.json
sw_vers -buildVersion
```

无显示器的构建宿主允许输出空列表；枚举失败返回非零。目标机上则必须能识别
`PhxAMDFB` 对应的内屏。`hi_dpi_2x=true` 只表示某个 CoreGraphics 模式的 backing
宽高恰好是逻辑宽高的两倍，**不表示该模式当前已选中、与 GOP 同尺寸或 GPU 加速成功**。
应同时核对 `current`、固件尺寸与下面的 framebuffer 属性。

从目标机当前 PhxAMDFB 会话的探针读取 `vendor_id` / `product_id`，从
`PhxFBWidth` / `PhxFBHeight` 读取物理尺寸。不要使用 PCI GPU ID `1002:1900`，
不要猜显示器 ID。此路径没有 DDC/EDID 读取，IOGraphics 可能给出
`0x756e6b6e`（`unkn`）/ `0x717` 等通用 ID；它们可匹配多台显示器，必须先确认
覆盖范围，不应在有相同 ID 的其他显示器时使用同一个覆盖文件。

以下 ID **仅为语法示例**，必须换成探针的实际结果：

```sh
python3 tools/phx_hidpi.py --vendor 0x1234 --product 0x5678 \
  --native 2560x1600 --out build/hidpi-review
```

输出为 `build/hidpi-review/DisplayVendorID-1234/DisplayProductID-5678` 和
`plan.json`。生成器只允许本仓库 `build/` 内的全新子目录，拒绝已有目录、
重定向到仓库外的 build 链接和系统位置；没有 install/apply、模式切换或 EDID 替换功能。
`plan.json` 的 `hardware_tested`、`installed`、`mode_changed` 和
`resampling_supported` 初始都为 false，不会因文件生成而变成 true。
奇数尺寸、超出 640..16384 × 400..16384 的尺寸和越界 ID 都会拒绝。

## 人工分阶段验收与回滚

仅在目标机现有 bring-up / 显示阶段已经稳定、操作者已审核候选构建与恢复入口后
进行。继续遵守 `BOOT-GATE.md` 和独立 EFI 仓库的流程；本次不替代那些门禁，
不修改安全设置，不写 NVRAM，也不自动安装驱动。每轮只改一个变量：

1. **A：同一候选构建、开关关闭、无新增覆盖文件。** 记录提交、真实 Tahoe OS build、
   原生像素尺寸、pitch、刷新率、探针的 `current` 和 mode 列表。先确认现有桌面正常。
2. **B：只增加 `phxfbhires=1`。** 保持其他已审核的启动参数与阶段不变。确认
   `PhxFBHiDPI=true`，预期逻辑宽高是物理尺寸的一半，物理尺寸和刷新率与 A 一致。
   该属性只证明开关/几何通过，不能证明 macOS 已选择 HiDPI。再次运行探针。
3. **C：保持 B，只增加已审核的覆盖文件。** 目标位置为
   `/Library/Displays/Contents/Resources/Overrides/DisplayVendorID-<hex>/DisplayProductID-<hex>`。
   先记录目的文件是否存在并保存恢复信息；若已存在，停止本步骤，不覆盖、不自动合并。
   同厂商目录可以保留，但只能新增本次审核的单个文件。由操作者按自己的系统维护
   流程手动放置和重新登录/启动；仓库工具不执行此步骤。不要写封印的 System 目录。
4. 在系统显示设置中查看候选 2× 模式；若出现，由操作者选择后再次运行探针。
   对 2560×1600 示例，`current` 必须为逻辑 1280×800、像素 2560×1600，
   `hi_dpi_2x=true`；同样核对真实面板，不将示例尺寸当成机器事实。
5. 检查文字、光标、窗口边界与四角，无裁切/黑屏/拉伸；保持 A 的刷新率。
   验证 WindowServer 持续 present，随后分别检查模式往返和睡眠唤醒。性能和
   GPU 执行按原有独立验收记录，不能从 HiDPI 尺寸关系推导。

若 B 或 C 没有新模式、探针 current 仍为 1×、出现黑屏/裁切或尺寸不同，
结果记为未通过；不要通过声明硬件 scaler 或虚构额外时序来绕过。

**回滚：** C 只移除本轮新建的那个覆盖文件，保留父目录和其他文件，回到 B；
B 移除 `phxfbhires=1` 回到 A。若无法进入桌面，使用既有恢复启动入口禁用实验
驱动并恢复已知可用状态。不要清空整个 Overrides、重置 NVRAM 或修改内置 Windows EFI。
再次运行探针，确认恢复到 A 的当前模式和物理尺寸。

只提交经过清理的结论、OS build、模式尺寸/刷新率与测试提交；本地 JSON、完整日志、
截图、原始 IORegistry/EDID、个人 EFI 和硬件标识都不纳入公开仓库。
可用以下只读过滤查看所需 framebuffer 属性，避免保存整份 IORegistry：

```sh
ioreg -r -c PhxAMDFB -d 1 -l | grep -E '"(PhxFBHiDPI|PhxFBHiDPILogicalWidth|PhxFBHiDPILogicalHeight|PhxFBWidth|PhxFBHeight|PhxFBRefreshMilliHz)"'
```

## CI 证据边界

`.github/workflows/hidpi-validation.yml` 在 `macos-15-intel` 上运行覆盖文件单测、
实际 framebuffer 回调的 ASan/UBSan harness、整个 PhxAccel 的原生编译/链接/签名
与 Mach-O 身份检查，并构建/运行只读探针。没有上传二进制或安装/加载 kext。
CPU harness 使用真实 `getInformationForDisplayMode()` 方法，断言只有标志改变，
物理尺寸、刷新率和拒绝路径保留；它不模拟 CoreDisplay，也不执行 GPU 命令。
已完成的结果另记于 `docs/validation/`；目标验收必须满足上节标准。
