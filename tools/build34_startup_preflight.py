#!/usr/bin/env python3
"""Offline build34 startup-order candidate; never installed by importing it.

Run the same complete installed/EFI validators before awaiting guardian
readiness. Each validator remains serial; an independently running guardian
may overlap its own work. The caller must retain its exact EFI lock, receipt/
PID validation, failure/recovery checks, final framebuffer/hold gates, original
shell and recovery dispatcher. No hardware, file, process or policy API is
used here. This helper alone is not a deployment scope or a boot-speed fix.
"""

import math
import time


READINESS_SECONDS = 45.0
POLL_SECONDS = 0.1


def preflight_before_guardian(*, installed_checks, verify_disk,
                             guardian_ready, validate_guardian, guard,
                             monotonic=time.monotonic, sleep=time.sleep):
    """Perform full checks once, then require a live guardian within 45 seconds.

    ``guard`` must raise for a pending failure/recovery or changed live jobs.
    ``validate_guardian`` must verify the original current-boot receipt, age
    and root-owned live guardian PID. A successful callback may return None;
    its return value is never substituted for validation. Preserve exceptions
    unchanged so the existing caller can record and dispatch its own recovery.

    The fixed deadline starts before validation, includes validation and receipt
    checking, and never resets when readiness appears. It does not interrupt a
    blocked callback; external worker limits and the EFI-lock timeout remain
    necessary. No thread, retry, digest cache, skipped check or shell launch is
    introduced. The final framebuffer/hold gates still belong to the caller.
    """
    previous = monotonic()
    if not math.isfinite(previous):
        raise ValueError("invalid startup readiness clock")
    deadline = previous + READINESS_SECONDS

    def boundary():
        nonlocal previous
        guard()
        now = monotonic()
        if not math.isfinite(now) or now < previous:
            raise ValueError("invalid startup readiness clock")
        previous = now
        if now >= deadline:
            raise TimeoutError("installed guardian readiness deadline")
        return now

    boundary()
    installed_checks()
    boundary()
    verify_disk()
    boundary()
    while True:
        ready = guardian_ready()
        if type(ready) is not bool:
            raise TypeError("guardian readiness must be boolean")
        now = boundary()
        if ready:
            break
        sleep(min(POLL_SECONDS, deadline - now))
    validate_guardian()
    boundary()
