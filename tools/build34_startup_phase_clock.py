#!/usr/bin/env python3
"""Bounded, process-local CPU timing; no startup, admission or deployment logic."""

from functools import wraps
import re
import time


class PhaseClock:
    """Observe synchronous calls while preserving their results and exceptions.

    Nested records overlap. Monotonic clock origins are not compared between
    processes. The sink must be separately secured and pinned by its caller.
    A failed sink stops an otherwise successful call; it cannot hide the
    original exception from a failed call. Calls still run after the record
    budget is exhausted, without collecting more records.
    """

    def __init__(self, sink, *, limit=256, wall_ns=time.monotonic_ns,
                 cpu_ns=time.process_time_ns):
        if type(limit) is not int or not 1 <= limit <= 1024:
            raise ValueError("phase clock requires a record limit from 1 to 1024")
        self.sink = sink
        self.limit = limit
        self.wall_ns = wall_ns
        self.cpu_ns = cpu_ns
        self.issued = 0
        self.stack = []

    def call(self, phase, action, *args, **kwargs):
        if not isinstance(phase, str) or re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", phase) is None:
            raise ValueError("phase clock requires a fixed, non-sensitive label")
        if self.issued >= self.limit:
            return action(*args, **kwargs)
        self.issued += 1
        sequence = self.issued
        parent = self.stack[-1] if self.stack else None
        wall = self.wall_ns()
        cpu = self.cpu_ns()
        self.stack.append(sequence)
        error = None
        try:
            return action(*args, **kwargs)
        except BaseException as caught:
            error = caught
            raise
        finally:
            self.stack.pop()
            try:
                end = self.wall_ns()
                record = dict(sequence=sequence, parent_sequence=parent, phase=phase,
                              start_monotonic_ns=wall, end_monotonic_ns=end,
                              elapsed_ns=end-wall,
                              process_cpu_ns=self.cpu_ns()-cpu,
                              status="error" if error is not None else "returned")
                if error is not None:
                    record["error_type"] = type(error).__name__
                self.sink(record)
            except BaseException:
                if error is None:
                    raise

    def wrap(self, phase, action):
        @wraps(action)
        def observed(*args, **kwargs):
            return self.call(phase, action, *args, **kwargs)
        return observed
