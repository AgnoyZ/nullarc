# Build34 R3 staged submit receipts

November 21, 2026: the source-only R3 protocol now has an experimental submit
operation returning the same complete identity accepted by the earlier wait
and ACK operations. This is not native capability/session admission, a Mesa
wire adapter or a deployable kernel. The hardware reader stays null, all
permanent client/service retention remains, and all 172 protected production
inputs and the installed build34 configuration remain unchanged.

## Submit contract

The original MIT [wire header](../tools/build34_exact_submit_wire.h) reserves
selector **66** only in the staged experiment, after wait/ACK selectors 64/65.
It includes the existing native submission structures with their unchanged
provenance and layout; it does not change the production native ABI header.
Its fixed 2,112-byte little-endian inband request consists of:

| Offset | Field | Bytes |
| --- | --- | --- |
| 0 | wire version and full envelope size | 8 |
| 8 | owner epoch | 8 |
| 16 | two reserved zero words | 16 |
| 32 | existing `phxn_cs_in` header | 32 |
| 64 | 64 existing `phxn_cs_ib` records | 2,048 |

The declared IB count must be 1–64, and every unused IB record must be zero.
Scalar, descriptor, asynchronous and variable-output shapes are refused.
Input and output sizes must match exactly. The request is copied once before
the handler acquires the client lock, supporting unaligned and overlapping
inband buffers without re-reading mutable input after a queued lock.

Under that lock, the handler requires Hello, the pinned embedded registry's
client/provider identity, both terminal gates and a matching owner epoch.
The owner is an identity counter, not an authorization credential. An eventual
native session handshake must supply it; today only the CPU fixture requests
exact mode before start. Legacy clients cannot obtain this operation simply
by guessing an existing owner.

The [transform](../tools/build34_exact_submit_receipt.py) derives a separate
typed exact-submit helper from the actual already-tested staged `doSubmit`.
It preserves existing context/IB/address/mapping/flag validation and the
actual service submission, including R1b queue-space retries. The old submit
method is unchanged. Additional exact-only restrictions are:

- All IBs must request one engine. The service may still select its existing
  fallback queue; the reply records the **actual** queue and generation.
- CPU user-fence requests are refused. Their per-submission exact publication
  and visibility protocol is not implemented; the old pending-fence slot is
  not silently treated as an exact-fence solution.
- No GPU-ready path means refusal, never the legacy mock immediate success.

A successful submit publishes the owned reservation before the actual
ring/writeback/doorbell writes, then returns the registry's receipt, not a
reconstructed sequence-only identity. The 64-byte reply reuses the earlier
receipt layout with status **3 submitted**. It carries owner, serial, slot,
sequence, generation and queue; reserved bytes are zero. No global prefix
or completion/CPU-visibility guarantee accompanies submission.

Only a successful, terminal-gate-rechecked operation writes output. An error
after packet publication can therefore be uncertain: the published receipt
and all resources stay retained, and the caller must not retry as though
nothing was submitted. Cancellation can remove only an unpublished Reserved
entry. Full receipt capacity refuses before dispatch; as in the previous
typed submit, validation/cache flush/VM setup are not represented as a
transaction with no side effects.

## Validation and limits

The [CPU runner](../tools/test_build34_exact_submit_receipt.py) freezes and
hash-checks the previous experiments, native ABI and protected production
inputs. It extracts the actual staged submit, service, external dispatcher,
wait and ACK methods. Existing methods and legacy dispatch are checked
byte-for-byte, apart from the new route before the client lock. Unrelated
legacy handlers are stubs. A separately compiled C peer uses fixed offsets
to encode requests and validate replies; it is not the production Mesa client.

ASan/UBSan and TSan each pass **212,170 additional checks in 2,371 groups and
seven real-thread scenarios**, plus **4,983** inherited binding checks.
All **15 defective variants** are detected at runtime. The checks cover
submit → pending wait → completed wait → ACK → stale
token refusal, actual queue fallback and full-width sequence/generation,
all 128 homogeneous batch shapes, mixed-engine and user-fence refusal,
malformed shapes and length sweeps, a full 64-entry table and slot reuse.
Seven real-thread cases cover input modification after capture and client or
service closure before dispatch, during packet emission and before output.
Published work remains retained on uncertain failure. Deliberately defective
variants test the identity, copy, shape, queue, output and terminal checks.
See [sanitized evidence](validation/build34-r3-submit-receipt-offline-20261121.json)
for the final counts, frozen hashes and preserved CPU fixture failures.

```sh
nice -n 15 taskpolicy -b make -j1 test-build34-exact-submit-receipt \
  EXACT_SUBMIT_RECEIPT_OUT=build/build34-r3-submit-receipt-new-private
```

No complete native translation unit, actual Kernel SDK, MIG/IOKit path or GPU
is exercised. In particular, CPU byte doubles do not prove native kernel
stack use, inband transport delivery or final OSObject lifetime. Capability
and session admission, independent genuine global-prefix/visibility and CPU
fence publication, Mesa binding/backpressure integration, a trusted device
reader, healthy drain and native completion events remain outstanding.
The [R3 ledger](BUILD34-R3-PLAN.md) still requires native integration and real
GPU/FPS/stability acceptance. Do not build or deploy the quarantining staged
source. There is no changed installed state to roll back; keep accepted
R1b/R2a/plugin/startup settings and the R4–R6 hold.
