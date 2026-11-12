# Base-shader translation sharing experiment

Date: 2026-11-12. Scope: `src/nmplugin`, downstream branch for Radeon 780M.
This is an original downstream implementation of request coalescing, inspired
by the pattern reviewed in NullMoth `7412cdd`. No reference source/binary was
copied; the existing PolyForm Noncommercial licence and notices remain intact.
No hardware execution, deployment, cold-start latency or FPS result is claimed.

## What changes

`nvmtl_compile_library_entry()` still checks the existing disk cache first.
Only overlapping misses enter the sharing registry. A SHA-256 identity covers
length-framed **full AIR bytes, actual AIR text, shader stage and translator
tag**, with a versioned domain separator. Display/log names are not translation
inputs. Keys do not depend on a writable cache path, so missing/write-failing
disk caches can still share work. A cache hit does not compute this new key.
Callers must not mutate translation inputs concurrently, as for the existing
translator API. The key helper does not truncate multi-gigabyte inputs to a
32-bit CommonCrypto length.

One owner runs the existing translator and synchronous disk-cache publication;
attached callers receive the immutable result or the same failure text. The
registry monitor protects only admission, result publication and statistics;
translation, disk I/O and waiting never hold it. Different keys remain parallel.
Returned translator buffers are freed in `@finally`, including failed or
exceptional translator exits. An exceptional owner still signals its waiters
with a failure, then propagates its own exception.

- The registry tracks at most **64 active owners**. At capacity, a new key
  runs the original path independently rather than growing the registry.
- A waiter waits at most the configured monotonic dispatch deadline
  (**30 seconds** in production). A timeout runs that caller independently;
  it cannot remove or publish another owner's entry. The translation itself
  is not cancelled or given a new deadline, and the dispatch API is not a
  real-time scheduling guarantee.
- Same-thread recursive requests bypass sharing to avoid waiting on themselves.
- Completed entries are removed immediately. Attached callers retain their
  result until they return; there is **no persistent success/failure cache**
  added here. A later miss retries normally, including after a failure.
- Presence of `NVMTL_TRANSLATE_COALESCE_OFF` disables sharing for rollback/A/B.
  `NVMTL_SPVCACHE_OFF` retains its existing disk-cache read semantics; it does
  not disable in-flight sharing or change the existing write behavior.

The existing `gSpvMiss` counts request-level disk misses, not unique translator
invocations. `nvtrace` adds a cumulative snapshot of owners, joins, bypasses,
timeouts, active entries and peak entries; these do not establish GPU execution.
Peak applies to tracked entries, not total translator concurrency after bypass.
Distinct inputs, saturation, recursion and timeout may still translate in
parallel. Function-constant/link/reflection/address-lowering caches, background
prewarming, cache-file formats and asynchronous disk I/O are unchanged.

## Verification and acceptance

`python3 tools/test_translation_flight.py --out build/translation-flight`
extracts the actual current base-translation function and compiles it with the
real sharing header on macOS. The translator, disk-cache access and logging are
fakes. The runner rejects missing/duplicate definitions and records input and
actual-entry hashes. `--sanitizer thread` selects ThreadSanitizer separately
from the default ASan/UBSan run. Native execution is not a Windows/Linux pass.

The deterministic concurrency fixture gates the owner while 31 callers attach,
then checks 32 requests caused one actual fake-translator call, one buffer free
and at most one cache write. It separately exercises success, failure,
exception and disk-cache-disabled batches; later retry, disk hits, direct
SPIR-V and missing-backend refusal; full key identity and framing; two different
keys inside the translator simultaneously; simulated registry saturation;
same-thread recursion; a copied mutable key; a **50 ms test-only** waiter
deadline whose timeout leaves the original owner intact; and 1600 actual-entry
requests across 16 workers. Test normal deadlines are 10 seconds; no test
substitutes a completion result or a GPU write.

Native CI results must be recorded after the run finishes. A synthetic
32-to-one translator-call count is not a cold-start speedup or FPS ratio.
Remaining target acceptance: active driver revision and actual OS/build,
unchanged shader output, cold/warm workload latency and frame-time evidence,
bounded memory, and sharing-on/off A/B with the same physical raster and
workload. Keep this experiment separate from prewarming or asynchronous I/O
so each measured change has one cause. Revert its source commit or use the
process-local disable variable for rollback; do not change EFI or installed
drivers as part of repository work.
