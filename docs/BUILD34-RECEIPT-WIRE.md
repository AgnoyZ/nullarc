# Build34 R3 complete-token receipt operations

November 21, 2026: this is an **experimental staged-source interface**, not
the installed native ABI or a deployable kernel. It follows the internal
wait-pinned ACK experiment, keeps all previous methods unchanged, and adds
complete-token wait/ACK handlers plus their actual `externalMethod` route.
The production native ABI and all 172 protected production inputs remain
unchanged. There is still no native request assigning exact mode, capability
negotiation, exact-submit reply or paired Mesa wire binding. Do not advertise
or enable this interface until the complete R3 admission ledger closes.

## Request and reply

The new [header](../tools/build34_exact_receipt_wire.h) is original MIT C/C++
interface code. Its version-1 structures are exactly 64 bytes, with explicit
size/offset assertions. It refuses compilation on a non-little-endian host.
Selectors **64 (wait) and 65 (ACK)** are reserved only within this staged
experiment. Each test checks that neither collides with the frozen legacy
selector enum. They are not an AMD/NVIDIA standard or a stable public ABI.

| Request offset | Field | Size |
| --- | --- | --- |
| 0 | version, size | two uint32 |
| 8 | owner | uint64 |
| 16 | serial | uint64 |
| 24 | sequence | uint64 |
| 32 | generation | uint64 |
| 40 | slot, queue | two uint32 |
| 48 | timeout_ns | uint64 |
| 56 | reserved, zero | uint64 |

Owner, serial, sequence and generation must be nonzero and not UINT64_MAX.
Slot must be below 64 and queue below two. The request version and size must
match; reserved must be zero. Timeout must not exceed two seconds; ACK requires
zero timeout. These are counter/queue identities, never kernel pointers or
cryptographic credentials. Existing user-client access control is separate.

| Reply offset | Field | Size |
| --- | --- | --- |
| 0 | version, size, status, reserved0 | four uint32 |
| 16 | owner, serial, sequence, generation | four uint64 |
| 48 | slot, queue | two uint32 |
| 56 | reserved | uint64 |

Status is **0 complete**, **1 pending** or **2 acknowledged**, according to the
operation. The identity echoes the captured request, with all reserved bytes
zero. No global retirement watermark is returned. Do not substitute a target
or a client-local completion summary for the independently required safe
global prefix in the Mesa completion cache.

The staged handler accepts exactly one synchronous, fixed-size inband
structure request/reply: no scalars, descriptors, variable output or async
notification fields. It verifies the argument selector and current argument
version, nonnull buffers and exact structure lengths before copying input.
The input is copied once with `memcpy`; unaligned and overlapping buffers are
supported. Reply bytes are written only after the operation succeeds and both
terminal gates are rechecked. On error the provided kernel-side output buffer
is unchanged. This CPU test does not establish MIG's userspace error-buffer
delivery behavior or the current SDK's complete argument layout.

## Bound identity and lifetime

The [source transform](../tools/build34_exact_receipt.py) derives two new
methods from the earlier tested wait/ACK while preserving their original
sequence-based internal methods. Under the client lock,
`Registry::authenticate` checks the actual owned slot/serial and matches
sequence, queue and generation. An emitted upper bound or a matching sequence
alone cannot authenticate a receipt. Incorrect complete tokens are rejected
before any device observation; stale tokens cannot name a reused slot.

A wait pins that exact ticket once, retains its whole-method callback lease,
and never resolves a sequence again after sleep. Real monotonic elapsed-time
budgeting and the two-second cap are inherited. The wire handler captures the
original clock before parsing and the outer handshake lock; that same origin
is passed into the typed wait, so queueing cannot restart the budget. Zero budget observes once;
positive pending waits yield with both locks released. Every terminal path
unpins under the client lock, including close and loss.

ACK authenticates the entire token, observes the actual queue/generation,
and forgets only completed metadata when all admitted waiters have left.
Pending or wait-pinned records return Busy. Missing records return NotFound;
that result must never be reinterpreted as a successful earlier ACK after
uncertain transport. Client/service closure or invalid observation returns
NotReady; malformed requests return BadArgument. These errors leave output
untouched. A successful forget followed by closure before reply can therefore
be an uncertain ACK outcome requiring paired-client fail-closed handling.

The **actual staged externalMethod** routes these operations before acquiring
the legacy client lock. The handler and wait take their own appropriate locks;
moving the route under that lock is caught as a nonrecursive-lock violation
by the CPU fixture. Legacy dispatch is otherwise byte-for-byte unchanged.
A public service helper checks the private terminal gate without granting
the client direct access to service-private storage.

No operation here flushes BOs, publishes a CPU user fence, raises global
retirement, releases a VMID or reclaims GPU resources. The permanent native
client/service quarantine remains. Receipt metadata removal cannot stand in
for healthy native resource drain or object/callback lifetime validation.

## Interface review and validation

The two pinned primary Apple XNU files and separate APSL-2.0 header review are
listed in [the interface source manifest](validation/build34-r3-receipt-interface-sources-20261121.json).
They establish the version-2 argument fields and the reviewed synchronous
bridge's initialization of selector/version, async fields and inband versus
descriptor fields. No upstream implementation was copied. The CPU double is
hand-authored and extends the previous test double only; the referenced XNU
commit is **not** claimed to match the installed kernel or SDK.

The [runner](../tools/test_build34_exact_receipt.py) compiles actual extracted
staged entrypoints, binding, submit, observer and wait/ACK methods against CPU
objects. A separate [C peer](../tests/test_build34_exact_receipt_peer.c) writes
and validates fixed byte offsets independently of C++ structure assignment.
It is not Mesa's production wire adapter or an IOKit client. Legacy handlers
unrelated to this dispatch are CPU stubs; no full native translation unit,
Kernel SDK or device runtime is compiled or opened.

ASan/UBSan and TSan each pass **372,707 additional checks in 320 groups and
five real-thread scenarios**, plus the unchanged **4,983 binding**, **22,094
wait** and **228,946 ACK** checks. Coverage includes:

- Every identity component, foreign clients, 1,024 paired slot-reuse rounds,
  stale/mixed tokens and full-width sequence/generation values.
- Exact length sweeps, version/reserved/null/count/descriptor/async rejection,
  zeroed replies, byte-exact error output, unaligned and overlapping buffers.
- A paused wait with input rewritten, another paused wait closed by the
  client, and one stopped by the service. ACK cannot remove a pinned receipt.
- Two outer-handshake-lock queueing cases prove that an already expired
  pending wait never sleeps again, while completion observed after queueing
  still wins. The clock origin is not recaptured after that lock.
- Deterministic closure after completed observation but before reply, plus
  the prior real-time, full-capacity, waiter-saturation and lifecycle tests.

All **20 defective variants** are detected, including omitted identity fields,
authentication bypass, request reread, early output, incorrect lock placement,
missing pin/final gate checks, a budget restart after the outer lock and
32-bit reply truncation. The default CPU
suite passes with its existing optional-firmware skip. See
[sanitized evidence](validation/build34-r3-receipt-offline-20261121.json).

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-receipt \
  EXACT_RECEIPT_OUT=build/build34-r3-receipt-new-private
```

Native mode/capability and submit negotiation, the independent prefix and
visibility/CPU-fence protocol, coherent hardware reader, healthy teardown,
events, actual SDK integration and real GPU/FPS/stability acceptance remain
required. Keep this transform unapplied to installed code; there is no new
deployed state to roll back. The accepted R1b/R2a/plugin/startup configuration
stays unchanged, R3 remains active, and R4–R6 remain pending.
