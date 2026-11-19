#!/usr/bin/env python3
"""CPU-only checks for interval accounting and refusal of misleading captures."""

import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("phase_analysis",
    Path(__file__).resolve().parents[1]/"tools/analyze_build34_startup_phases.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def record(sequence, parent, phase, start, end, cpu=1):
    return dict(sequence=sequence, parent_sequence=parent, phase=phase,
                start_monotonic_ns=start, end_monotonic_ns=end,
                elapsed_ns=end-start, process_cpu_ns=cpu, status="returned")


class PhaseAnalysisTests(unittest.TestCase):
    def rows(self):
        return [record(1, None, "main", 0, 100, 60),
                record(2, 1, "checks", 10, 70, 40),
                record(3, 2, "hash", 20, 50, 30),
                record(4, 1, "checks", 80, 90, 5)]

    def test_nested_totals_are_not_added(self):
        result = m.summarize_records(self.rows())
        self.assertEqual(result["root_elapsed_ns"], 100)
        self.assertEqual(result["root_process_cpu_ns"], 60)
        self.assertEqual(result["by_phase"]["main"]["exclusive_elapsed_ns"], 30)
        self.assertEqual(result["by_phase"]["checks"]["inclusive_elapsed_ns"], 70)
        self.assertEqual(result["by_phase"]["checks"]["exclusive_elapsed_ns"], 40)
        self.assertEqual(sum(x["exclusive_elapsed_ns"] for x in result["by_phase"].values()), 100)

    def test_completion_order_does_not_change_result_or_mutate_input(self):
        rows = self.rows();before = copy.deepcopy(rows)
        self.assertEqual(m.summarize_records(list(reversed(rows))), m.summarize_records(rows))
        self.assertEqual(rows, before)

    def test_process_clock_origins_are_not_emitted(self):
        rows = self.rows();shifted = copy.deepcopy(rows)
        for row in shifted:
            row["start_monotonic_ns"] += 123456789
            row["end_monotonic_ns"] += 123456789
        self.assertEqual(m.summarize_records(rows), m.summarize_records(shifted))

    def test_budget_hit_is_not_a_complete_timing_claim(self):
        result = m.summarize_records(self.rows(), limit=4)
        self.assertTrue(result["potentially_incomplete"])
        self.assertFalse(m.summarize_records(self.rows())["potentially_incomplete"])

    def test_errors_are_reported_without_private_exception_details(self):
        rows = self.rows();rows[2].update(status="error", error_type="ValueError", message="private")
        result = m.summarize_records(rows)
        self.assertFalse(result["all_calls_returned"])
        self.assertEqual(result["by_phase"]["hash"]["errors"], 1)
        self.assertNotIn("private", repr(result))

    def test_duplicate_or_missing_sequences_refused(self):
        for rows in [self.rows()+[self.rows()[0]], self.rows()[1:]]:
            with self.assertRaises(ValueError):m.summarize_records(rows)

    def test_cycle_forward_parent_and_missing_parent_refused(self):
        for parent in (2, 3, 999, True):
            rows = self.rows();rows[1]["parent_sequence"] = parent
            with self.assertRaises(ValueError):m.summarize_records(rows)

    def test_child_outside_parent_refused(self):
        rows = self.rows();rows[2].update(end_monotonic_ns=75, elapsed_ns=55)
        with self.assertRaises(ValueError):m.summarize_records(rows)

    def test_overlapping_siblings_or_roots_refused(self):
        for parent in (1, None):
            rows = self.rows();rows[3].update(parent_sequence=parent, start_monotonic_ns=60, elapsed_ns=30)
            with self.assertRaises(ValueError):m.summarize_records(rows)

    def test_bad_duration_integer_and_labels_refused(self):
        for field, value in [("elapsed_ns", 99), ("process_cpu_ns", -1),
                ("sequence", True), ("start_monotonic_ns", 0.5),
                ("phase", "/private/path"), ("status", "pending")]:
            rows = self.rows();rows[0][field] = value
            with self.assertRaises(ValueError):m.summarize_records(rows)

    def test_nonmonotonic_sequence_refused(self):
        rows = self.rows();rows[3].update(start_monotonic_ns=15, end_monotonic_ns=16, elapsed_ns=1)
        with self.assertRaises(ValueError):m.summarize_records(rows)

    def test_invalid_budget_or_empty_capture_refused(self):
        for limit in (True, 0, 1025, 3):
            with self.assertRaises(ValueError):m.summarize_records(self.rows(), limit=limit)
        for rows in ([], None, [None]):
            with self.assertRaises(ValueError):m.summarize_records(rows)


if __name__ == "__main__":
    unittest.main()
