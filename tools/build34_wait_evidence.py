#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Independently parse the pinned two-dispatch native probe, never execute it.

The caller must pin the probe source/binary, actual loaded R1a kernel, current
boot and independent desktop gates. Text alone is not hardware acceptance.
"""
import json

SUCCESS = ("DIAGNOSTIC-PASS: original34 preamble=single; two guarded dispatches; "
           "no driver or display acceptance")
BUDGETS = (0, 50000, 2000000000)


def parse(stdout, stderr, returncode):
    if type(returncode) is not int or returncode != 0 or stderr:
        raise ValueError("native probe did not exit cleanly")
    if not stdout.endswith("\n"):
        raise ValueError("incomplete native output")
    lines = stdout.splitlines()
    if not lines or lines[-1] != SUCCESS or not 3 <= len(lines) <= 7:
        raise ValueError("missing exact two-dispatch success or unexpected output")
    rows = [json.loads(line) for line in lines[:-1]]
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"pass", "budget_ns", "busy", "elapsed_ns"}:
            raise ValueError("unexpected wait fields")
        if any(type(v) is not int for v in row.values()):
            raise ValueError("noninteger wait evidence")
        if row["pass"] not in (0, 1) or row["busy"] not in (0, 1) or row["elapsed_ns"] < 0:
            raise ValueError("invalid wait state or clock")
    if [row["pass"] for row in rows] != sorted(row["pass"] for row in rows):
        raise ValueError("dispatch order differs")
    for index in (0, 1):
        group = [row for row in rows if row["pass"] == index]
        if not group or [row["budget_ns"] for row in group] != list(BUDGETS[:len(group)]):
            raise ValueError("missing, duplicated or unreviewed wait budget")
        if group[-1]["busy"] != 0 or any(row["busy"] != 1 for row in group[:-1]):
            raise ValueError("missing positive completion or wait after completion")
    return dict(status="passed-two-dispatch-native-output-and-cleanup",
                native_submissions=2, whole_arena_checks_passed=2,
                same_IB_rewritten_between_dispatches=True, clean_client_teardown=True,
                waits=rows, pending_return_observed=any(row["busy"] == 1 for row in rows),
                positive_budget_wait_calls=sum(row["budget_ns"] > 0 for row in rows),
                wall_time_return_deadline_proved=False, physical_FPS_measured=False)
