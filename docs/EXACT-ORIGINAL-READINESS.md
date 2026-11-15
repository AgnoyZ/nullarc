# Original startup with publication-aware Metal observation

Preparation snapshot, 2026-11-15: **a fresh external observer is staged but not
armed.** It corrects the demonstrated premature Metal check in the
[consumed exact-original trial](EXACT-ORIGINAL-TRIAL.md). No postboot success
is claimed. This continues the owner's accepted entirely-original test under
the same disclosed reference-layout risk; it does not reuse an old allowance.

## Single behavioral change

The installed upstream v0.4.0-alpha drivers, initialization helpers, firmware,
startup scripts/plist, watchdogs, Metal plugin and runtime remain byte-identical
to the retained release. The loaded PhxBringup image matches build 34. The
system remains x86_64 macOS **26.7.2 / 25G332**. The earlier reference physical
base and VRAM-extent conflict remains unresolved and explicitly accepted.

The original `PHX_FB` accelerator deliberately withholds `MetalPluginName`
until display arming or its 60-second headless callback. The prior kernel logs
confirmed this behavior, but the old external probe failed before the callback
could run. The fresh observer therefore waits for the original accelerator's
actual plugin-name and class properties before running the **same unchanged
Metal verifier once**. It does not restore the property itself or write a
display-arming sysctl. Absence alone cannot cause an early Metal probe.

The publication wait has a 120-second cap and reserves 45 seconds within the
existing independent 300-second boot deadline. Disappearance, a wrong plugin
name/class or the deadline causes the existing safe-state recovery. A probe
exit-code receipt is added for observation; the native executable and its
shader, zero-initialized output, completion limit and result requirement are
unchanged. A published plugin alone is never accepted as GPU execution.

## Preserved boot and recovery limits

The unchanged upstream LaunchDaemon still performs initialization. The external
observer invokes no initializer and requests the desktop boot only after
original startup, image identity and actual Metal execution all pass, with the
original one-shot flag present. Desktop acceptance still requires another real
Metal result, increasing frame counters, the expected display gates and a
stable WindowServer without a new diagnostic report.

There are at most two managed ordinary reboot requests and one managed recovery
request in this new packet. Exclusive intent receipts prevent retry; ambiguous
shutdown calls are never repeated. The original script's own watchdog/recovery
requests remain separate and unchanged. The independent initial-reboot timer
is 180 seconds and each observed trial boot has a 300-second deadline. The
unchanged original daemon can start before the observer ACK, and a hardware
hard hang can still prevent software recovery.

The trial is one-shot: restore GPU-off after the original off check, remove
persistent and one-shot display arming during the desktop stage, and keep the
next boot GPU-off even if the current desktop test succeeds. All consumed
installation and prior experiment packets remain closed. The old inactive
external witness plist was archived before installing this separate witness;
its original bytes, contract and receipts remain private and preserved.

## Preparation evidence

Thirty-one CPU-only methods passed. They retain the previous phase, refusal,
deadline and exclusive-reboot tests and add delayed/immediate publication,
missing/wrong publication, disappearance and deadline-reserve cases. The
waiter is tested with registry reads substituted and with command, probe and
marker operations forbidden. These methods run no real GPU or shutdown command.

The first staging comparison refused before any new packet/job or arming
write because the prior original startup created `fwaddr.log`. Independent
readback found that this generated diagnostic was the only extra file; no
release input was missing or changed. The revised preflight requires that
exact observed log metadata and retains the file. Only this output is excluded
from immutable input pins, because the unchanged upstream startup overwrites
it. Tests verify that changed/missing output and other unexpected files cannot
silently normalize away modified inputs. The raw log stays private.

Fresh full-file comparisons passed after that classification. The root-owned
packet pins **1,697 inputs**, including **1,656 frozen interpreter files**.
Its LaunchDaemon/interpreter path executed the unarmed preparation role and
exited with GPU-off retained and no display flags, GPU initialization or reboot
request. The [sanitized record](validation/exact-original-readiness-20261115.json)
distinguishes this preparation snapshot from future execution.

Read root-owned intent, publication, probe, stage and recovery receipts before
continuing. Never dispatch again after an existing arm/reboot intent. Do not
modify a consumed contract or observer, reinstall the fork, change EFI,
partitioning, BIOS/security settings or reset NVRAM. Only the scoped upstream
display flag is used and cleared by the bounded test.
