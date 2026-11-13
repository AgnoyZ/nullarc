# 启动编排门禁（phx_boot_gate.sh）

本文件说明 `tools/phx_boot_gate.sh`：它是实验驱动的**启动阶段执行器与失败保护外壳**，用来替代
参考实现 `tools/phxctl/full.sh`、`bringup5.sh`、`phxboot.sh` 里的控制流，而不是它们的寄存器序列。

> 状态：源码与 POSIX shell 测试已完成，Linux CI 执行；**未在 macOS / 目标机运行，也未提供
> 安装流程**。它自身不会初始化 GPU，只负责"按顺序、可中止、可回退地"运行经过审核的阶段程序。

## 为什么需要它

`docs/BRINGUP-AUDIT.md` 记录了参考工作流的控制流问题：

- `full.sh`、`bringup5.sh` 把固件/寄存器命令接在 `grep`、`tail` 之后且没有 `pipefail`，
  失败可能被管线最后一个成功命令掩盖；
- 两个脚本都会先挂一个 `shutdown -r +N` 看门狗，再在末尾 `killall shutdown`；
- `phxboot.sh` 失败路径会自动重启、写/删 NVRAM 变量、改 sysctl、按进程名杀 WindowServer，
  并且日志只落在一个共享目录里。

这些行为在没有实机审核的情况下不能进入本仓库。门禁把其中**安全可复用**的部分固定下来：
有序阶段、超时、首个失败即停、退出路径上的释放钩子、崩溃标记、kill switch 和私有日志。

## 契约

```sh
sh tools/phx_boot_gate.sh --state DIR --stages DIR --expected-build N \
    [--release PATH] [--timeout SECONDS] [--check]
```

- `--state DIR`：私有状态目录（不存在则创建为 0700）。放标记、锁、日志与每个阶段输出。
  `--check` 时不需要。
- `--stages DIR`：阶段目录。其中的**非隐藏文件必须可执行**，按文件名字节序执行
  （建议 `00-firmware`、`10-psp`、`20-mes`、`30-claim`）。存在不可执行或文件名含异常字符的
  文件时整体拒绝，避免"某个阶段没加执行位而被静默跳过"。
- `--expected-build N`：要求 PhxBringup 的 `phx-build` 属性等于该值。
- `--release PATH`：释放钩子的绝对路径，在门禁取得锁之后的**每一条退出路径**上执行一次，
  带 15 秒上限。典型内容是上游 `phxboot.sh` 的 `sysctl -w debug.phxfb_hold=0`：失败时
  必须解除 PhxAMDFB 的持有，否则 WindowServer 可能打不开内屏。
- `--timeout SECONDS`：单阶段上限，默认 60。
- `--check`：只读校验主机、kext 属性和阶段列表，打印计划，然后什么都不做、不写状态。

### 预条件（只读）

| 检查 | 失败退出码 |
| --- | --- |
| `uname -s` 为 Darwin | 74 |
| `uname -m` 为 x86_64 | 74 |
| `ioreg -r -c PhxBringup` 可见 | 79 |
| `phx-780m-policy` 为 `strict-execution-v1` | 79 |
| `phx-build` 等于 `--expected-build` | 79 |
| `phx-fb-phys` 与 `phx-fb-aper-len` 均为非零 | 79 |

属性由 `PhxBringup` 在 `start` 中发布（见 `src/phxbringup/PhxBringup.cpp`），因此门禁不需要
任何参考机地址常量：它只确认"是这颗 780M、是这个 build、帧缓冲布局已发布"。

### 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 全部阶段成功；或 `--check` 通过；或 kill switch 生效 |
| 64 | 参数、路径或阶段目录不合法 |
| 74 | 主机不是 Darwin x86_64 |
| 75 | 另一个门禁实例正在运行 |
| 76 | 上次尝试未完成（标记存在），本次不执行阶段 |
| 77 | 某个阶段返回非零 |
| 78 | 某个阶段超时 |
| 79 | kext 属性与策略/期望 build 不符 |

### 失败语义

- **阶段失败/超时**：删除标记，记录原因，仍然执行释放钩子，返回 77/78。这是"已处理失败"，
  下次启动可以重试。
- **门禁被信号杀死（含挂死）**：`SIGTERM`/`SIGINT` 会触发清理并执行释放钩子，但**保留标记**；
  `SIGKILL` 连清理也不会发生，标记同样保留。下次启动看到标记就以 76 拒绝执行阶段，并执行
  释放钩子——也就是保持固件 framebuffer，等人工检查后删除标记。
- **陈旧锁**：锁目录里记录 PID；PID 已不存在时视为上一次实例被杀死，记录后替换锁继续；
  PID 仍存活则返回 75，且不执行释放钩子（避免干扰正在运行的实例）。
- **kill switch**：`$STATE/off` 存在时什么都不做（但仍释放），返回 0。

状态目录内容：`gate.log`、`attempt.pending`、`gate.lock/pid`、`results.txt`、
每个阶段的 `stage-<name>.out` 与超时标记 `stage-<name>.timeout`、`release.out`。
全部按 `umask 077` 创建。

## 它不会做的事

静态测试会检查脚本正文（忽略注释）里不出现：`shutdown`、`reboot`、`nvram`、`killall`、
`sysctl`、`/Users/Shared`、`Library/GPUBundles`。也就是说门禁本身：

- 不重启、不关机、不写/删 NVRAM；
- 不按名字杀进程，只终止自己启动的阶段和钩子；
- 不安装、不复制、不改 EFI、不改系统安全设置；
- 不内置任何寄存器、地址或固件偏移常量。

它同样**不是**一个可用的 GPU 初始化器：真正的阶段命令仍要由 `tools/phxctl/phxctl`、
`tools/phxctl/mesboot` 的已审计入口提供，而这两个工具仍带有选定的 VRAM 偏移和寄存器
编程，尚未完成参数化与实机验证（见 `BRINGUP-AUDIT.md`、`IMPLEMENTATION-STATUS.md`）。

## 使用示例（不安装）

```sh
# 只读检查：不会写任何状态
sudo sh tools/phx_boot_gate.sh --check --stages /path/to/reviewed-stages --expected-build 33

# 真正运行：状态目录与阶段目录都必须是绝对路径
sudo sh tools/phx_boot_gate.sh --state /private/var/phxgate --stages /path/to/reviewed-stages \
    --expected-build 33 --release /path/to/release-hold.sh --timeout 60
```

本仓库不提供 LaunchDaemon、安装脚本或默认阶段目录；是否把它接进开机流程属于部署决定，
必须单独评审并准备回退。

## 验证

`tests/test_boot_gate_shell.py` 在 POSIX shell 上运行真实脚本（Windows 跳过，Linux CI 执行），
用假的 `uname`/`ioreg`、阶段脚本与释放钩子覆盖：阶段顺序、首个失败即停、超时、标记拒绝、
kill switch、活跃锁与陈旧锁、主机与 kext 预条件、`--check` 不写状态、参数与阶段目录清理，
以及脚本正文不含重启/NVRAM/杀进程原语。

本地（Windows）只做了 `sh -n` 语法检查和 Git Bash 手工 smoke（顺序、失败、超时、标记、
陈旧锁、信号中断后保留标记），不构成平台证据。

## 分配失败调查中的额外边界

2026-11-14 的[初始化接口审查](ALLOCATION-INITIALIZER-CONTRACT.md)把当前完整 `mesboot` 入口
（仅链接 fake IOKit）作为阶段接入本脚本，验证布局拒绝和传输失败会保留阶段状态、阻止后续
替身阶段，并执行释放替身。另一个 FIFO 场景表明：阶段仍在等待时，释放钩子尚未执行；解除
claim 替身中的等待后才会进入后续阶段及释放钩子。这是同步控制流证据，不是 GPU 挂死或独立恢复证明。

因此，分配调查要求的独立恢复不能依赖本脚本等待阶段结束后才运行的释放钩子；用户态超时
也不证明不可中断内核调用一定可终止。已处理失败会删除 pending marker 的原有语义同样不能
代替一次性显示授权的持久消费记录。本次未改变脚本、超时、返回码或 AGDC 恢复策略，未连接
已装启动项，也未执行真实初始化、显示放行或重启。
