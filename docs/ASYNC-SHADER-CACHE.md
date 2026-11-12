# Bounded background base-SPIR-V persistence

Original downstream implementation under the existing `src/nmplugin` PolyForm
Noncommercial licence. No reference-project code or binaries are copied.

## Scope and behavior

Only the base-library AIR-to-SPIR-V cache write moves off the calling thread.
The translator itself remains synchronous. Index/key memo files, specialized
shader caches and address lowering are unchanged. This is an experimental host
control-flow optimization; it does not establish target acceleration or FPS.

After a successful translation, an immutable result and full translation key
are retained in a process-local pending map. A serial utility-QoS dispatch queue
persists the result using the existing checked, unique-temporary-file,
`fsync`/close/atomic-rename writer. No I/O runs under the pending-map monitor.
Stored-byte and stored-entry counters advance only on successful persistence.
Writer statistics distinguish accepted/reused/skipped/completed/failed/exceptional
work and report pending count and bytes on the existing translation-miss trace.

Limits are **32 active-plus-queued entries** and **32 MiB of tracked pending
payload**, including the active writer. Object/key/path/block overhead, callers'
results and brief completed-block/autorelease lifetimes are outside that payload
accounting; this is not a process RSS limit. Mutable input data, keys and paths
are copied on acceptance. Duplicate full keys do not enqueue another write.
Full queues and oversized/unavailable identities skip disposable persistence
without falling back to blocking disk I/O. Shader results still return normally;
a later disk miss may translate again. There is no busy retry loop.

The existing disk-hit path remains first and avoids key creation/queue locking.
After a miss, the translation-sharing producer first checks pending results by
the **full AIR/text/stage/translator identity**. If absent, it rechecks disk to
cover a writer completing between the initial miss and producer execution.
Results retire from the pending map immediately after success, failure or a
caught Objective-C writer exception. Failure preserves the previous cache file,
does not invalidate the shader returned to the caller, and permits a later retry.
There is no persistent memory memo or negative cache.

## Switches, rollback and lifetime

- Presence of `NVMTL_SPVCACHE_ASYNC_OFF` restores synchronous base-cache writes
  and disables pending lookup/secondary disk lookup. Restart the application for
  a controlled A/B; do not mutate environment variables during concurrent calls.
- Existing `NVMTL_SPVCACHE_OFF` keeps its existing **read-disable** meaning:
  disk and pending-result reads are bypassed, while writes are still attempted.
- Existing `NVMTL_TRANSLATE_COALESCE_OFF` disables translation-flight sharing;
  pending cache reads remain available unless a cache-read/async switch disables
  them. Use both sharing and async switches when isolating translation counts.

There is deliberately no application-exit drain, shutdown hook or new durability
promise. Process exit may discard queued disposable files; a crash can leave an
unused unique temporary file, as with an interrupted synchronous write. Existing
validated files remain governed by atomic rename. Next launch regenerates a
missing cache. No driver installation or system configuration changes are made.

## Checks and target evidence still needed

`tools/test_async_cache.py` executes the actual entry and save wrapper, the actual
pending helper and actual atomic filesystem helper on macOS. The translator
produces synthetic 20-byte output. Fixtures hold `fsync` while the compile caller
returns, reuse the pending output 100 times, exercise retirement/recheck, fill
the entry/byte bounds including the active writer, mutate accepted inputs, inject
`fsync` failure and a store exception, preserve an older file, retry, check both
switches, and run 1600 requests on 16 workers. Separate ASan/UBSan and TSan runs
are required; a Windows/Linux source test is not Foundation execution.

Native results are recorded separately after CI completes. Real translator/shader
correctness, target OS build, cold/warm launch latency, queue pressure, memory and
frame-time distribution still need target A/B evidence before any speedup claim.
Keep workloads and all other knobs fixed. Rollback is the async-off switch and
an application restart, or a normal reviewed revert; no EFI deployment is implied.
