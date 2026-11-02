# 显示路径：VRAM 池释放与 scan-out 别名的重试

本文件记录补丁 `0028-checked-framebuffer-pool-and-alias-retry.patch` 的依据、实现边界和
目标机验收方法。它是源码修改说明，**不是实机验证结果**：本次没有 Mac 构建、没有加载
kext、没有在 ThinkBook 上接管内屏。

## 上游实现的实际路径

`src/phxaccel/accel/phxfb.cpp` 是 WindowServer 实际合成的那个 `IOFramebuffer`
（`PhxAMDFB`，类名带 `AMD`，CoreDisplay 据此认定厂商）。它按上游实现的做法工作：

1. 不重新点屏：接管固件（GOP/IONDRV）已经点亮的模式，scan-out surface 仍是启动控制台的
   那块内存（`IOPlatformExpert::getConsoleInfo`），只读地测量 OTG 的 H/V 总计和刷新率。
2. 加速器的显示通道不做 GPU 合成：每一帧由 CPU 拷进 scan-out 的映射，VBL 用定时器按实测
   刷新率代替真实中断来驱动 WindowServer 的节拍。
3. 因此 surface 的“VRAM”只是物理连续的系统内存；`nvAllocVram` 从启动时一次性取得的
   大池里切分（512/256/128 MB 依次尝试），`nvGpuVaAlloc` 返回的地址不进入页表。

上游注释记录了这条路径上已经踩过的两个真实故障，本补丁正是针对它们：

- **通过 BAR 拷贝一帧 2560×1600 约 110 ms（约 7 fps）**，整个桌面卡顿；只有通过
  carve-out 的系统内存别名（`phx-fb-phys`）访问时才是正常速度。别名建立后会抽样比对
  别名视图与 BAR 视图，不一致就退回 BAR 拷贝。
- **VRAM 逐笔分配在长时间会话后找不到物理连续段**，显示唤醒后 WindowServer 重新分配
  帧缓冲时面板停留在睡眠前的画面。这就是改用固定池的原因。

## 补丁改了什么

### 1. carve-out 未发布时不再耗尽检查预算

原实现里 `fAliasTries >= 3` 会永久放弃别名路径，而 `fAliasTries` 在**每一次** present 都加
一——即使 `phx-fb-phys` 还没被 `PhxBringup` 写出来。三条早期 present 就会把整个会话钉在
BAR 拷贝（约 7 fps）上，日志里只有一行“no system-RAM view”，看不出是时序问题还是像素不符。

现在把两种状态分开：

- carve-out 未发布 / 找不到所在 BAR / 地址相加会溢出：记一次 `fAliasWaits`，本次返回
  `nullptr`（继续走 BAR 拷贝），下次 present 再试；首次只打一行
  `alias: carve-out not published yet ... retrying`；
- 真正拿到候选视图并完成抽样比对：才增加 `fAliasTries`，像素不符仍最多 3 次，
  之后不再重复映射。

等待上限 `kAliasWaitLimit = 3600` 次 present，避免属性永远不出现时每帧做一次
IORegistry 扫描。

### 2. 池内释放先做整数范围校验

原实现直接做 `(uint8_t *)r->kva - fPoolKva` 求偏移：当句柄不属于本池时这是未定义行为，
且 `off + len > fPoolBytes` 在 `off` 被算成极大值时可能回绕，从而把**别的分配**的范围交给
`IORangeAllocator` 释放。

现在先把两个指针转成整数、确认 `kva >= base`，再用共享策略
`phx780m::poolReleaseValid(offset, len, poolBytes)` 校验：

```text
pageAligned(len) && (offset & 0xFFF) == 0 && rangeWithin(offset, len, poolBytes)
```

不满足就记录一行 `VRAM: release refused ...` 并返回 `kIOReturnBadArgument`，分配器状态不变。
合法的池内释放必然通过：`vramAlloc` 先用 `round_page_64` 取整，`poolAlloc` 又以
`PAGE_SIZE` 对齐切分，所以长度和偏移一定是页的整数倍且非零。

### 3. 池初始化失败时继续尝试更小的池

`IORangeAllocator::withRange` 失败时原实现 `return`，直接放弃整个池（退化为每笔分配各自
找连续内存），而不是尝试 `kPoolTry` 里更小的尺寸。改为 `continue`。

## 未改变的部分

- 不写显示引擎、不改模式、不改 panel timing，也不触碰 `phxAgdcInstall`、VBL 定时器、
  `measureRefresh` 的寄存器读取。
- 不新增安装/部署路径，不改 EFI、NVRAM 或系统安全设置。
- 未在目标机验证；`hardware_tested` 仍为 false。

## 与 nullarc 的对齐状态

| nullarc 组件 | 本仓库状态 | 说明 |
| --- | --- | --- |
| `src/phxbringup`（PSP/MES/GPUVM/BO/提交 ABI） | 已固定，27 个下游补丁加严 | 本次不涉及 |
| `src/phxaccel`（`NMXAccel` + `PhxAMDFB` + `PhxAGDC`） | 已构建；本次加固 VRAM 池与别名重试 | 显示引擎与面板时序仍按上游 |
| `src/nmplugin`（Metal over Vulkan 插件） | 已源码构建，仅补丁 0002 改运行库定位 | 其余行为未审计 |
| Mesa RADV / LLVM AIR / `libnvmtl_translate` | 已固定源码并构建 | 见 `UPSTREAM.md`、`IMPLEMENTATION-STATUS.md` |
| `tools/phxctl/phxboot.sh`、`full.sh` 启动编排 | **未接入**，仅审计 | 含参考机常量、自动重启与 NVRAM 显示接管；见 `BRINGUP-AUDIT.md` |
| `src/amd`、`src/kext`（旧 RDNA3 探索代码） | 保留在上游子树，不在构建内 | 与 `PhxBringup`/`PhxAccel` 是两条独立路线 |
| 外接显示、背光、视频编解码 | 上游未支持 | 不承诺 |

也就是说：本次“参照 nullarc 优化”落在显示路径的健壮性上，而不是引入参考机的常量或安装流程。

## 目标机验收清单

在 Tahoe 目标机安装实验 kext 之后（仍需独立评审与回退准备），逐项记录：

1. 启动日志出现 `VRAM pool: <N> MB at phys 0x...`；若为“no contiguous run”，说明池未建立，
   记录当时的可用内存与分配顺序。
2. 出现 `alias: carve-out not published yet ... retrying` 后，应在若干帧内出现
   `alias: scan-out at BAR offset 0x... = system RAM 0x...: X of X samples match the BAR (Y non-zero)`。
   若等待计数最终耗尽仍无该行，说明 `PhxBringup` 没有发布 `phx-fb-phys`，应作为独立问题
   跟踪，而不是调大等待上限。
3. 拖动窗口/滚动时的帧率与上游描述的 116–120 fps 量级对比；持续停留在 BAR 拷贝应表现为
   个位数到十几 fps。
4. 日志中不应出现 `VRAM: release refused`。若出现，记录 `kva`/`len` 与池大小——这意味着
   上层句柄与池不匹配，是新的兼容性问题，不能视为“只是多了个检查”。
5. 睡眠/唤醒后重新合成，确认面板内容会更新（对应上游“池碎片导致唤醒后画面不刷新”的场景）。

以上五条都需要真实 GPU 执行证据；在完成之前，本条目不构成加速成功的声明。
