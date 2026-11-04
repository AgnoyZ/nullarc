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

## 显示节拍策略：从内联表达式抽成可断言的头文件

`src/phxaccel/accel/nvrm-accel.cpp` 里三条“决定一帧怎么算画完、怎么计节奏、什么时候不再等
surface”的判断，原来散在函数体里，只能靠实机观察：

| 规则 | 原位置 | 现在的实现 |
| --- | --- | --- |
| 拷贝的帧在**下一个 VBL tick** 才完成；超过两个刷新仍无 tick 就强制完成（避免画面冻结） | `isTransactionComplete` | `phx780m::presentCompletion()` |
| 相邻两次拷贝的间隔按刷新数分桶（约 1 / 2 / 3 / ≥4 个刷新，即 `debug.nvaccel_iop_gap1..gap4`） | `performTransaction` | `phx780m::iopGapBucket()` |
| 同一个 head 最多连续压 4 帧，之后照旧拷贝（surface 永不同步也不能冻住面板） | `nvAccelSurfCopyReady` | `phx780m::nextCopyHold()` |

三条规则现在都在 `src/phxaccel/PhxPresentPacing.hpp`（纯函数，无 IOKit、无寄存器、无副作用），
由 `tests/test_present_pacing.cpp` 在 Linux CI 上断言，并**逐值对比**分桶规则与原始内联表达式
（含刷新周期为奇数时 `floor(3 * refresh / 2) != 1.5 * refresh` 的边界），所以节奏计数器与旧采集
仍然可比。

这仍然只是策略断言：它能证明“规则按预期工作”，不能证明“帧真的按时到了面板”。上表五条实机
验收一条都没变——尤其第 3 条帧率，只能靠真机的 `debug.nvaccel_iop_gap*` 与 `copy_us` 说话。

## 拷贝路径策略：一行像素走哪条路，以及窄化算得对不对

拷贝循环里还有一处只能靠实机才能发现错的地方：**一行像素实际走哪条路径**，以及**拷贝时把
ARGB2101010 窄化成 XRGB8888 的位运算**。两者同样抽进 `src/phxaccel/PhxCopyPath.hpp`：

| 规则 | 现在的实现 |
| --- | --- |
| 8 字节（两个像素）`movnti` 对：两侧 8 字节对齐、每行像素数为偶数 | `phx780m::wideEligible()` |
| 64 字节 SSE 行：两侧 16 字节对齐、跨度为 4 的倍数，且**必须** `debug.nvaccel_iop_sse=1` | `phx780m::sseEligible()` |
| SSE 每行取多少个 16 字（64 字节）步，其余部分交给后两条路径；不足一步的行完全不走 SSE | `phx780m::sseWords()` |
| 对循环从 SSE 边界按整对恢复，奇数尾字留给 4 字节循环（不重拷、不漏拷） | `phx780m::pairResume()` |
| 单像素窄化：ARGB2101010（A 31:30、R 29:20、G 19:10、B 9:0，每通道丢低 2 位）→ 不透明 XRGB8888 | `phx780m::narrowWord()` |
| 一次 64 位读入两个像素的窄化，断言与两次 `narrowWord()` 完全一致 | `phx780m::narrowPair()` |

`tests/test_copy_path.cpp`（Linux CI，ASan/UBSan）做三件事：把两条选择规则与抽取前的内联表达式
在地址 × 跨度的矩阵上**逐值对比**；把行切分（SSE 步数、对循环复位）与旧算式逐值对比；把窄化在
每个通道 1024 个取值、以及随机 64 位输入上验证（含“低 2 位确实被丢弃”“两像素一次处理
等于两次单像素处理”）。

这仍然只是策略断言：它证明位运算与选择规则按文档工作，**不证明面板上的颜色正确**——颜色要看真机
截图与 `debug.nvaccel_crc`，帧率要看 `copy_us`。

## 别名重试预算：把 0028 修的那个 bug 变成断言

补丁 0028 修的是"carve-out 还没发布时的 present 被当成校验失败"——三次早期 present 就把整个会话
钉在 BAR 拷贝（约 7 fps）。当时只有一段 staged-source 测试按**文本顺序**断言行号；现在这条语义
本身进了 `src/phxaccel/PhxHardwarePolicy.hpp`，由 `tests/test_hardware_policy.cpp` 断言：

| 规则 | 实现 | 断言里最重要的一条 |
| --- | --- | --- |
| 预算耗尽判定：3 次像素校验失败，或 3600 次等待 | `phx780m::aliasExhausted()` + `kAliasVerifyLimit` / `kAliasWaitLimit` | `aliasExhausted(0, 3599)` 为假——**3599 次等待一个校验预算都不花** |
| 能否映射并校验：必须同时拿到已发布的 carve-out 地址与 BAR 内偏移，且相加不回绕 | `phx780m::aliasCarveOutReady()` | 两者缺一即为"等待"，相加溢出也拒绝 |
| 采样步长：整屏约 4096 个采样点，至少 1 字 | `phx780m::aliasSampleStep()` | 2560×1600 字 → 每 1000 字一个采样 |
| 接受条件：全部采样一致，且至少一个非零 | `phx780m::aliasSamplesMatch()` | 全零视图（"看起来一致"）被拒绝，那是过期画面不是同一帧 |

驱动侧（`phxfb.cpp`）只保留三件事：计数顺序（先 `fAliasWaits++`，再 `fAliasTries++`，最后才
`IODeviceMemory::withRange`）、日志与状态；`tests/test_framebuffer_path.py` 现在断言它**调用**这些
策略函数并保持该顺序，不再断言魔法数字的字面文本。

依旧只是策略断言：它证明"等待不会吃掉预算"这类规则成立，不证明别名在真机上建立成功——那要看内核
日志里的 `alias: ... samples match the BAR` 行。
