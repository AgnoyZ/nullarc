# Build34 R3 raw-dword window callsites

November 21, 2026: the previously separate `FenceWindow32` primitive now has
a source-only integration into actual staged adoption, shared submission,
invalidation and exact observation. The raw-dword reader remains **null**.
This is not a drop-in kernel candidate: every staged `gpuSubmit`, including
legacy clients on those queues, now refuses without that admitted reader.
The installed build34, 172 protected production inputs, earlier experiments,
native ABI and runtime recipes remain unchanged. Permanent client/service
quarantine remains; do not compile or deploy this experiment as a kernel.

## Integration

The original MIT [transform](../tools/build34_exact_window.py) derives from
the submit-receipt checkpoint and includes the unchanged, separately tested
[window primitive](../tools/build34_exact_fence32.h). Window state lives
outside resettable queue history and is serialized by `gpuLock`.

- Actual adoption invalidates the old window and seeds a strictly newer
  generation with `gSeq`, before queue readiness is published. UINT64_MAX
  refuses before seeding or device-fence writes. The existing two-dword
  device seed, mapping and packet format are unchanged.
- Actual sleep/fault/stop invalidation closes both arithmetic windows as
  well as invalidating the existing queue identities. An old receipt never
  becomes live again after metadata re-adoption.
- `readExactFence32` validates queue lifecycle, logical aperture and actual
  map length, nonnull/nonoverflowing base and aligned four-byte access. Its
  separate raw-dword callback supplies only a uint32; no 64-bit or legacy
  callback fallback exists. A post-read terminal check precedes decoding,
  and failure preserves the caller's output.
- Exact observation passes that decoded value to the existing queue-bound
  registry classifier. The window's upper bound accounts for **every**
  submission through the staged `gpuSubmit`, including legacy callers and
  actual fallback queue selection, not only owned exact receipts.
- The ring-space loop now also reads through the bounded dword path before
  pruning history. It cannot treat an unrelated high dword as completion.
  Existing R1b yielding and its real monotonic two-second budget remain.
- Before VM binding, receipt publication or packet writes, a new sequence
  must be within the strictly less-than-2^32 global sequence interval. A
  large gap caused by the other queue counts even if this queue has only
  one job. Insufficient window space returns Busy without dispatch; there
  is no speculative mask, eviction, reseed or fabricated completion.
- The window upper bound commits after successful receipt publication and
  before the first packet write. A definitely rejected publication does not
  consume its sequence. Sequence exhaustion now refuses legacy callers too.

The raw callback must eventually prove a coherent, non-regressing aligned
device load, packet completion visibility and bounded nonblocking behavior.
No code in this change assigns it. Bounds checks and arithmetic do not prove
those device properties or effective mapping/cache attributes. In particular,
the prior whole-wrap stale-sample counterexample still applies.

## Tests

The [runner](../tools/test_build34_exact_window.py) freezes the actual staged
source and all prior inputs, then extracts the relevant methods into CPU
objects. Unrelated methods, the legacy global helper, old WAITSEQ and the
permanent retention paths are checked unchanged. VM binding in this fixture
is a counted stub; neither a complete native translation unit nor actual
SDK/IOKit/OSObject lifetime is exercised.

ASan/UBSan and TSan each pass **43,251 checks in 36 groups and four real-thread
scenarios**. All **13 defective variants** are detected at runtime. Coverage
includes full-width global sequences across low-word wraps; independent GFX
completion with earlier compute pending; legacy history reuse; actual queue
fallback; exact 2^32 span boundaries; failure-preserving publication, sampling
and output; null, short, misaligned and overflowing mappings; generation
loss/reseed; client/service close during a paused read; and serialized clients.

A specific CPU representation counterexample places a bogus high word above
an old low word on a full ring. Both exact and legacy staged submissions keep
the pending history, issue no new packet/VM binding and return Busy after
2,000 fake-clock yields. Restoring the old 64-bit ring-space read makes the
same assertion fail at runtime. This models a proposed unsafe representation;
it does not reproduce an installed-driver or GPU failure. No real two-second
hardware wait, frame-rate or performance measurement is claimed.

The earlier standalone arithmetic, receipt and ownership inputs remain
hash-frozen. Their test counts are not added to this callsite suite; the old
binding fixture's unrelated regression functions are compiled but not executed.
See [sanitized evidence](validation/build34-r3-window-callsites-offline-20261121.json).

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-window \
  EXACT_WINDOW_OUT=build/build34-r3-window-callsites-new-private
```

## Remaining native requirements

This closes a source-level gap between window arithmetic and queue callsites,
not the [reader contract](BUILD34-FENCE-READER.md) or [R3 ledger](BUILD34-R3-PLAN.md).
Queue re-adoption here proves metadata ordering only. It does not prove old
hardware writers drained, exclusive ownership, nonaliasing physical fences
or safe reuse of an adopted queue. Wide-gap recovery still needs proved drain
and reseed, rather than a silent arithmetic reset.

The unchanged `queueFence`/`gpuRetired`, watchdog, VM binding and timeout-release
consumers still need their own coherent observation and lifecycle audit.
In particular, this fixture's VM stub is not proof that the actual `vmBind`
uses a safe global watermark; nor does zero or failed retirement make the old
timeout cleanup safe. Native prefix/visibility and CPU user-fence publication,
capability/session admission, Mesa binding, healthy drain/reclamation, native
events and actual SDK integration remain outstanding. No installation, GPU
submission, restart, resident monitor or configuration change occurred.
Keep accepted R1b/R2a/plugin/startup settings; R3 remains active and R4–R6 stay
pending through actual GPU, FPS and stated-duration stability acceptance.
