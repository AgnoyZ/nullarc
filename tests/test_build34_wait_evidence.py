#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""CPU-only checks of native-wait evidence admission; no device calls."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("wait_evidence", Path(__file__).resolve().parents[1] / "tools/build34_wait_evidence.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class WaitEvidence(unittest.TestCase):
    def rows(self):
        return [dict(pass_=p, budget_ns=b, busy=busy, elapsed_ns=elapsed)
                for p in (0, 1) for b, busy, elapsed in ((0, 1, 1500), (50000, 0, 52000))]

    def output(self, rows=None):
        if rows is None:
            rows = self.rows()
        return "\n".join([*(json.dumps({("pass" if k == "pass_" else k): v for k, v in row.items()}) for row in rows), m.SUCCESS]) + "\n"

    def refused(self, rows):
        with self.assertRaises(ValueError):
            m.parse(self.output(rows), "", 0)

    def test_pending_then_completion(self):
        result = m.parse(self.output(), "", 0)
        self.assertEqual(result["whole_arena_checks_passed"], 2)
        self.assertTrue(result["pending_return_observed"])
        self.assertEqual(result["positive_budget_wait_calls"], 2)

    def test_immediate_completion_does_not_claim_pending_coverage(self):
        rows = [dict(pass_=p, budget_ns=0, busy=0, elapsed_ns=1000) for p in (0, 1)]
        result = m.parse(self.output(rows), "", 0)
        self.assertFalse(result["pending_return_observed"])
        self.assertEqual(result["positive_budget_wait_calls"], 0)

    def test_real_late_return_is_recorded_not_hard_deadline_proof(self):
        rows = self.rows(); rows[1]["elapsed_ns"] = 1000000
        self.assertFalse(m.parse(self.output(rows), "", 0)["wall_time_return_deadline_proved"])

    def test_nonzero_exit_or_stderr_refused(self):
        for stderr, code in (("FAIL", 0), ("", 75), ("", False)):
            with self.assertRaises(ValueError): m.parse(self.output(), stderr, code)

    def test_truncated_or_missing_success_refused(self):
        for text in (self.output()[:-1], self.output().replace(m.SUCCESS, ""), ""):
            with self.assertRaises(ValueError): m.parse(text, "", 0)

    def test_missing_pass_refused(self): self.refused(self.rows()[:2])
    def test_out_of_order_passes_refused(self): self.refused(list(reversed(self.rows())))

    def test_unknown_or_duplicate_budget_refused(self):
        for budget in (1, 0, 2000000001):
            rows = self.rows(); rows[1]["budget_ns"] = budget; self.refused(rows)

    def test_pending_at_end_refused(self):
        rows = self.rows(); rows[-1]["busy"] = 1; self.refused(rows)

    def test_wait_after_completion_refused(self):
        rows = self.rows(); rows[0]["busy"] = 0; self.refused(rows)

    def test_noninteger_negative_clock_and_unknown_fields_refused(self):
        for key, value in (("busy", True), ("busy", 2), ("elapsed_ns", -1), ("pass_", 2), ("extra", 0)):
            rows = self.rows(); rows[0][key] = value; self.refused(rows)

    def test_capped_third_wait(self):
        rows = []
        for p in (0, 1):
            for b, busy in ((0, 1), (50000, 1), (2000000000, 0)):
                rows.append(dict(pass_=p, budget_ns=b, busy=busy, elapsed_ns=1000))
        self.assertEqual(m.parse(self.output(rows), "", 0)["positive_budget_wait_calls"], 4)


if __name__ == "__main__": unittest.main()
