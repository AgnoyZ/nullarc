# 两个候选 kext 的手动升级与回退

适用：已经安装 nullarc、可进入 macOS 的 Radeon 780M `1002:1900` / Darwin 25
测试机。下载包不是完整安装包，不包含固件、Metal 插件、运行库或自动安装器。
首次安装请先阅读仓库 INSTALL.md；不能靠这两个文件建立完整加速环境。

## 1. 核对下载并保留回退

在 macOS 解压后运行 `shasum -a 256 -c SHA256SUMS`，再分别运行
`codesign --verify --strict PhxBringup.kext` 和
`codesign --verify --strict PhxAccel.kext`。保存 build-report.json 和源码 SHA。
不凭包版本号或 phx-build 数字判断是否是本次构建。

先确认备用启动盘确实可启动。备份完整可用 EFI、原
`/Library/Extensions/PhxAccel.kext`、
`/Library/KernelCollections/AuxiliaryKernelExtensions.kc`、现有 PhxGPU 插件/运行库
及 `/Users/Shared/gpu` 的启动脚本。确认实际启动的是哪个 EFI，不把桌面副本视为
已部署。不要覆盖 Windows 的 Microsoft/Boot 目录。

**先核对已安装插件/运行库与候选的 ABI 和行为兼容性。两者都叫 build 34 并不
证明兼容。只有两个 kext 的下载包，不能视为当前完整栈的已验证替代品。**
未确认恢复路径或兼容性前停在下载、校验和备份阶段。

## 2. 测试 EFI：PhxBringup

只在单独的测试 EFI 中，用包里的 PhxBringup.kext 替换
`EFI/OC/Kexts/PhxBringup.kext`。保留原 Kernel/Add 条目：
BundlePath=PhxBringup.kext，ExecutablePath=Contents/MacOS/PhxBringup，
PlistPath=Contents/Info.plist，MinKernel=25.0.0，Enabled=true。

下游候选还要求 boot-args 包含 `phx780m=1`。保留现有其它参数；不要为此重置
NVRAM、修改 BIOS、套用参考机 ACPI 或再次降低系统安全设置。
不要把 PhxAccel 加到 OpenCore 的 Kernel/Add。

## 3. macOS：PhxAccel 与辅助内核集合

PhxAccel 的目标是 `/Library/Extensions/PhxAccel.kext`，不是 EFI。
在备份并完成兼容性核对后，由操作者替换该 bundle，保持 root:wheel 所有权和
不可由 group/other 写入的权限，再通过已审核的现有流程重建辅助内核集合。
仅复制文件而不重建集合，重启后可能仍使用旧代码。

本包不提供一键系统写入命令。上游 `tools/phxctl/kinst.sh` 会发布新的辅助内核
集合，必须先检查 kmutil 成功、候选 bundle 身份和需要保留的其它 kext，再发布。
不要为了“加载成功”忽略 kmutil 失败或绕过签名错误。仓库的其它 deploy 脚本
可能写固定内部 EFI，不能直接用于这台电脑。首次测试保持现有 WindowServer
启动策略，不把更换插件、开启新优化和调整输入轮询混在同一轮。

## 4. EDID 测试是额外的显式配置

新 EDID 回调在 PhxAccel 内，需要 GPU 自身的真实 `phx-edid` Data 属性。
本机此前准备的私有 DeviceProperties 片段应由操作者合并进测试配置，不能覆盖
整个 config.plist。不要使用测试夹具的假 EDID。比较原生 EDID 时，在测试配置
中禁用旧 ThinkBookPanelEDID.kext，避免混淆来源；其余测试先保持原状。
驱动没有增加 AMD AUX/I2C 自动读取，也不会把当前 60 Hz 模式切换为 120 Hz。

## 5. 手动重启后只读检查

```sh
sw_vers
ioreg -r -c PhxBringup -d 1 -l | grep 'phx-build'
ioreg -r -c PhxAMDFB -d 1 -l | grep -E 'PhxFB(EDID|Refresh|Width|Height)'
```

若使用已验证的 128 字节面板数据，EDID 预期为 Valid=true、Bytes=128、
Source=phx-edid、Status=valid，并私下比对显示节点的原始字节。
服务缺失时先检查候选加载/启动门控；签名成功不能证明内核已加载它。
进一步检查桌面、亮度、物理模式/刷新率和睡眠唤醒。显示模式、VBL 定时器、
提交速率与应用 FPS 分开记录；不能靠系统信息的 Metal 字样认定稳定 120 FPS。

## 6. 回退

启动异常时使用已验证备用 EFI/恢复环境。恢复同一套旧 PhxBringup、PhxAccel
及对应辅助内核集合；若改过插件/运行库/启动脚本也一起恢复。恢复测试配置中
原有的 EDID 注入设置，只移除本次新增属性和参数，保留之后的其它独立改动。
仅恢复 EFI 不能撤销 macOS 内的 PhxAccel 更新。恢复后手动重启并复核原有桌面。

## 新版 PhxBringup 与旧启动工具

仅替换 kext 时，旧 `bringup5.sh` 缺少显式 PSP 布局配置，raw TOC/TMR
请求也不会建立新版固件加载所需的就绪状态。兼容修订增加了默认关闭的
`phx-legacy-boot` 配置入口：校验本机显存布局，并把这两个旧请求转入受检查流程。
**单独替换修订版 kext 仍不等于启用兼容模式。**

详见 [LEGACY-BOOT.md](LEGACY-BOOT.md)。离线工具只生成局部 DeviceProperties
片段，不能替换完整 `config.plist`。本机内存布局和片段必须留在忽略的 `build/`
目录，不要提交或上传。该修订尚未经过目标 GPU 验证；不自动部署到工作 EFI。

启动后先核对 GPU 的 PCI provider 上有完全一致的 128 字节 Data，且服务的
`phx-legacy-boot-status=0`、`phx-legacy-boot-startup-enabled=true`。
状态属性缺失时先排查注入，不能当作布局被拒绝；配置文件和 EFI 属性块中有数据
也不代表 macOS 已把它交给 GPU。核对本机 ACPI 根节点 `_UID` 和全部 PCI 路径，
不要沿用示例的 `PciRoot(0x0)`。未通过前保留自动初始化保护，不运行旧 full.sh。
该属性只在驱动启动时读取，修正路径后须由操作者再次手动重启并复核。
