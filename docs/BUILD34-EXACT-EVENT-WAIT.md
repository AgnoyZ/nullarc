# Build34 R3 staged completion event wait

## NullMoth reference

The review pins `nullmoth/nvidia-macos-driver` at
`87e524ab36f12d17c04626d6cf7fc3bde1cc63e4`. The
[NVK patch](https://github.com/nullmoth/nvidia-macos-driver/blob/87e524ab36f12d17c04626d6cf7fc3bde1cc63e4/nvk/nvk-macos.patch)
registers one RM graphics non-stall event per device on a dedicated connection,
and frees the RM registration before closing that connection. The graphics
event is broader than an exact submission: NVK checks the pending channels'
slots, generations and semaphore values independently. It reads the event
count before rechecking those targets. The kernel
[event handler](https://github.com/nullmoth/nvidia-macos-driver/blob/87e524ab36f12d17c04626d6cf7fc3bde1cc63e4/kexts/NVRM/NVRM.cpp)
increases the connection counter on delivery, then wakes sleepers. Selector 6
uses a compare, enrollment and post-enrollment recheck, with a global sleeper
cap and a timeout. NVK requests 2 ms on that path and falls back to polling
without a supported graphics event. Its wait-block policy defaults to event
waits in WindowServer and polling in ordinary apps. The
[RTX 5060 results](https://github.com/nullmoth/nvidia-macos-driver/blob/87e524ab36f12d17c04626d6cf7fc3bde1cc63e4/docs/EVENT-WAIT.md)
showed lower CPU time from app opt-in and higher elapsed latency in the short
compute workload. They do not predict 780M FPS or latency.

The NVRM source declares PolyForm Noncommercial 1.0.0, also the reference
repository's default. The NVK patch edits Mesa and the repository separately
provides Mesa notices. This stage implements the ordering independently and
copies no source, binaries, selector, interrupt routing or hardware policy.

## Build34 experiment

Only the offline transform changes: the pinned exact receipt's wait can
snapshot a queue-specific notification counter before observing its fence.
The provider compares the same counter under `gpuLock` before atomically
enrolling with a backend that drops the lock while sleeping. If notification
arrived between observation and enrollment, it rechecks the fence without
sleeping. The client lock is released before sleep. The existing authenticated
ticket and wait pin remain held across retries. Only fence observation can
prove the requested sequence completed. Other-queue and old-generation
notifications cannot wake that wait as completion evidence, and the counter
cannot wrap into a previously observed value. No global retirement or resource
reclamation method is changed.

The sleep interval is at most 1 ms and clipped to the remainder of the
original monotonic request budget. Its absolute deadline must be anchored to
the timestamp passed to the backend. Timeout and wake both lead to another
observation. An early return with no notification change takes one polling
turn after that observation. If no backend is available, the existing 1 ms
polling path applies. Both paths can overshoot with scheduler delay; neither
promises a hard return deadline. Stop and queue invalidation wake affected
waiters; client close is noticed at recheck, within the requested slice plus
scheduling and lock delay if already asleep. A wake never grants device
visibility, successful completion, or queue drain.

## Verification and remaining work

The [offline runner](../tools/test_build34_exact_event_wait.py) exercises the actual staged receipt wait, event and
invalidation methods with CPU lock/clock/registration doubles. The tests
cover notification on both sides of enrollment, missing or spurious wakes,
old and wrong-queue notifications, two concurrent GFX waiters, stop and
generation invalidation, and GFX completion while earlier compute is pending.
It also checks the complete staged driver before and after with the pinned
SDK/KDK as nonloadable objects. ASan/UBSan and TSan each passed 481 checks;
five intentionally broken variants failed as expected. The 377 declared
imports and 172 production inputs are unchanged. See the
[sanitized results](validation/build34-r3-event-wait-offline-20261121.json).
Run sequentially at background priority:

```sh
nice -n 15 taskpolicy -b python3 -B tools/test_build34_exact_event_wait.py \
  --out build/build34-r3-event-wait-new-private --sdk "$KERNEL_SDK" --kdk "$KDK"
```

The event backend stays null. Before binding, establish the actual AMD event
source and deferred callback context, an admission limit for kernel sleepers,
the native atomic wait primitive and deadline conversion, and safe shutdown of
the source and all enrolled waiters. Prove BAR fence visibility and external
writer drain independently, then measure real wait/latency and FPS along with
dual-queue correctness and sustained desktop stability. No installation, GPU
submission or restart was performed. Rollback is to omit the offline transform.
