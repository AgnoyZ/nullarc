#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Finite read-only display trace recipe/parser; importing never starts tracing."""
import math


TRANSACTION = '_ZN14NMXDisplayPipe18performTransactionEP30IOAccelDisplayPipeTransaction2'
WAIT = '_ZL15nvSurfWaitReadyj'
PREPARE = '_ZL20nvAccelSurfCopyReadyP9IOSurfacej'
SECONDS = 8
# Verified final popq %rbp offsets in the accepted a206d983 PhxAccel image;
# this host's FBT return probes report that byte, immediately before retq.
# A different
# image needs its own disassembly check; do not infer actual returns from a
# tail-call helper's return probe (see R1b's rejected measurements).
BASELINE_RETURNS = (0x7ac, 0x162, 0x405)


def trace_program():
    # IOAccelerator can call the transaction on a kernel workloop rather
    # than WindowServer's process thread. Scope by the exact kext/method,
    # and retain only that thread's nested display-stage observations.
    return f'''#pragma D option quiet
#pragma D option bufsize=2m
#pragma D option dynvarsize=256k
#pragma D option switchrate=20hz
dtrace:::BEGIN {{ self->txn = (uint64_t)0; printf("READY %llu\\n", (uint64_t)timestamp); }}
fbt:com.luuumi.PhxAccel:{TRANSACTION}:entry
/self->txn/
{{ printf("REENTER\\n"); }}
fbt:com.luuumi.PhxAccel:{TRANSACTION}:entry
{{
    self->txn = timestamp; self->wait = (uint64_t)0; self->prep = (uint64_t)0;
    self->wc = (uint64_t)0; self->wf = (uint64_t)0; self->pf = (uint64_t)0;
    self->ws = (uint64_t)0; self->ps = (uint64_t)0;
    printf("ENTRY %d %llu %d\\n", tid, (uint64_t)self->txn, pid);
}}
fbt:com.luuumi.PhxAccel:{WAIT}:entry
/self->txn/
{{ self->ws = timestamp; }}
fbt:com.luuumi.PhxAccel:{WAIT}:return
/self->txn && self->ws/
{{
    self->wait += timestamp - self->ws; self->wc++; self->wf += arg1 == 0;
    printf("WAIT_RETURN %llu\\n", (uint64_t)arg0); self->ws = 0;
}}
fbt:com.luuumi.PhxAccel:{PREPARE}:entry
/self->txn/
{{ self->ps = timestamp; }}
fbt:com.luuumi.PhxAccel:{PREPARE}:return
/self->txn && self->ps/
{{
    self->prep += timestamp - self->ps; self->pf += arg1 == 0;
    printf("PREPARE_RETURN %llu\\n", (uint64_t)arg0); self->ps = 0;
}}
fbt:com.luuumi.PhxAccel:{TRANSACTION}:return
/self->txn && (self->ws || self->ps)/
{{ printf("UNFINISHED_STAGE\\n"); }}
fbt:com.luuumi.PhxAccel:{TRANSACTION}:return
/self->txn/
{{
    printf("TX %d %llu %llu %llu %llu %llu %llu %llu %llu %llu\\n", tid,
        (uint64_t)self->txn, (uint64_t)timestamp, (uint64_t)self->wait,
        (uint64_t)self->prep, (uint64_t)self->wc, (uint64_t)self->wf,
        (uint64_t)self->pf, (uint64_t)arg0, (uint64_t)arg1);
    self->txn = 0;
}}
dtrace:::ERROR {{ printf("ERROR\\n"); }}
profile:::tick-{SECONDS}sec {{ exit(0); }}
dtrace:::END {{ printf("END %llu\\n", (uint64_t)timestamp); }}
'''


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        raise ValueError('no complete transaction samples')
    return dict(count=len(ordered), minimum_ns=ordered[0],
                median_ns=ordered[(len(ordered) - 1) // 2],
                p95_ns=ordered[math.ceil(.95 * len(ordered)) - 1],
                maximum_ns=ordered[-1], sum_ns=sum(ordered))


def parse(text, code=0, stderr='', *, returns=BASELINE_RETURNS):
    if code != 0 or stderr:
        raise ValueError('trace failed or reported diagnostics')
    begin, end, entries, transactions, waits, prepares = [], [], {}, [], [], []
    for line in text.splitlines():
        if not line.strip():
            continue  # DTrace adds a final blank line on this host.
        words = line.split()
        try:
            tag, values = words[0], [int(v) for v in words[1:]]
        except ValueError as e:
            raise ValueError('non-numeric trace record') from e
        if any(v < 0 for v in values):
            raise ValueError('negative trace value')
        if tag in ('READY', 'END') and len(values) == 1:
            (begin if tag == 'READY' else end).append(values[0])
        elif tag == 'ENTRY' and len(values) == 3:
            key = tuple(values[:2])
            if key in entries:
                raise ValueError('duplicate transaction entry')
            entries[key] = values[2]
        elif tag == 'TX' and len(values) == 10:
            transactions.append(values)
        elif tag in ('WAIT_RETURN', 'PREPARE_RETURN') and len(values) == 1:
            (waits if tag == 'WAIT_RETURN' else prepares).append(values[0])
        else:
            raise ValueError('unknown, incomplete or error trace record')
    if len(begin) != 1 or len(end) != 1 or end[0] <= begin[0]:
        raise ValueError('missing or duplicate trace lifecycle')
    if not transactions:
        raise ValueError('no complete transaction samples')
    paired, last = set(), {}
    for r in sorted(transactions, key=lambda x: (x[0], x[1])):
        tid, start, stop, wait, prep, wc, wf, pf, offset, result = r
        key = (tid, start)
        if (key not in entries or key in paired or not begin[0] <= start < stop <= end[0]
                or start < last.get(tid, 0) or wait + prep > stop - start
                or wc > 1 or wf > wc or pf > 1 or offset != returns[0] or result):
            raise ValueError('unpaired, overlapping, invalid or failed transaction')
        if wf or pf:
            raise ValueError('surface wait or copy readiness failed')
        last[tid] = stop
        paired.add(key)
    if any(v != returns[1] for v in waits) or any(v != returns[2] for v in prepares):
        raise ValueError('stage endpoint is not an admitted actual return')
    if len(waits) < sum(r[5] for r in transactions):
        raise ValueError('missing observed surface-wait return')
    return dict(entry_count=len(entries), completed_transactions=len(transactions),
                incomplete_at_trace_end=len(set(entries) - paired),
                kernel_context_entries=sum(v == 0 for v in entries.values()),
                transaction=distribution([r[2] - r[1] for r in transactions]),
                surface_wait=distribution([r[3] for r in transactions]),
                copy_prepare=distribution([r[4] for r in transactions]),
                residual_including_copy_and_other_work=distribution(
                    [r[2] - r[1] - r[3] - r[4] for r in transactions]),
                failures=0, physical_FPS_measured=False)
