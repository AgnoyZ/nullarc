#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate finite R1b probe output and matching kernel queue-space sleeps."""


def parse(probe, trace, probe_exit, trace_exit, diagnostics):
    if probe_exit != 0 or trace_exit != 0 or diagnostics.strip():
        raise ValueError("probe failed, trace diagnostics, or trace did not exit")
    cmp, gfx, arena = {}, {}, {}
    warm = False
    lines = probe.splitlines()
    if not lines or lines[-1] != "DONE pressure probe; both connections closed":
        raise ValueError("clean end marker missing")
    ordered_seq = set()
    for ln in lines[:-1]:
        label, *fields = ln.split()
        b, i, *v = map(int, fields)
        if label == "CMP" and 1 <= b <= 4 and 1 <= i <= 4 and len(v) == 3:
            begin, end, seq = v
            if not 0 < begin < end or not 0 < seq < (1 << 64) - 1 or seq in ordered_seq or (b, i) in cmp:
                raise ValueError("invalid compute submission")
            ordered_seq.add(seq)
            cmp[b, i] = begin, end, seq
        elif label == "GFX" and len(v) == 5 and ((b, i) == (0, 0) or 1 <= b <= 4 and 1 <= i <= 10):
            begin, end, seq, before, after = v
            if not 0 < begin < end or not 0 <= before < seq <= after < (1 << 64) - 1 or seq in ordered_seq or (b, i) in gfx:
                raise ValueError("GFX fence failed to prove completion")
            ordered_seq.add(seq)
            gfx[b, i] = begin, end, seq
            warm |= (b, i) == (0, 0)
        elif label == "ARENA" and 1 <= b <= 4 and 0 <= i <= 10 and v == [16384] and b not in arena:
            arena[b] = i
        else:
            raise ValueError("unexpected or duplicate probe record")
    if set(cmp) != {(b, i) for b in range(1, 5) for i in range(1, 5)} or not warm or set(arena) != {1, 2, 3, 4}:
        raise ValueError("incomplete submissions or arena verification")
    if set(gfx) != {(0, 0)} | {(b, i) for b, n in arena.items() for i in range(1, n + 1)}:
        raise ValueError("incomplete GFX sequence")
    for events in (cmp, gfx):
        previous_end, previous_seq = 0, 0
        for event in sorted(events):
            begin, end, seq = events[event]
            if begin < previous_end or seq <= previous_seq:
                raise ValueError("overlapping or unordered client records")
            previous_end, previous_seq = end, seq

    rows = trace.rstrip("\r\n").splitlines()
    if len(rows) < 2 or rows[0] != "READY" or rows[-1] != "END":
        raise ValueError("incomplete trace")
    sleep_threads, waits, overlaps, durations = set(), 0, 0, []
    for row in rows[1:-1]:
        label, *fields = row.split()
        if label != "WAIT_BLOCK" or len(fields) != 6:
            raise ValueError("unrecognized trace record")
        thread, w0, w1, t0, t1, identity = map(int, fields)
        if identity != 2 or thread <= 0 or not 0 < w0 < w1 or not 0 < t0 < t1 or abs((w1-w0)-(t1-t0)) > 100_000:
            raise ValueError("unverified callsite or inconsistent trace clocks")
        if t1 - t0 < 500_000:
            raise ValueError("truncated or nonblocking sleep interval")
        matches = [(b, i) for (b, i), (start, end, _) in cmp.items() if start < w0 < w1 < end]
        if not matches:
            continue  # The short trace can also capture the setup/teardown period.
        if len(matches) != 1:
            raise ValueError("ambiguous compute call")
        sleep_threads.add(thread)
        waits += 1
        durations.append(t1 - t0)
        burst, _ = matches[0]
        overlaps += sum(w0 + 100_000 <= begin < end <= w1 - 100_000
                        for (b, _), (begin, end, _) in gfx.items() if b == burst)
    if len(sleep_threads) != 1 or not waits or not overlaps:
        raise ValueError("no GFX completion wholly inside a verified compute queue-space sleep")
    return {"compute_burst_submissions": len(cmp), "gfx_submissions_including_warmup": len(gfx),
            "full_arenas_per_queue": len(arena), "arena_bytes": 16384, "paired_pressure_sleeps": waits,
            "gfx_completions_inside_pressure_sleep": overlaps, "both_clients_closed": True,
            "minimum_pressure_sleep_ns": min(durations), "maximum_pressure_sleep_ns": max(durations)}
