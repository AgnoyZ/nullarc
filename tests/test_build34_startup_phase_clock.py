#!/usr/bin/env python3
"""CPU-only timing transparency, bounded output and failure-propagation checks."""

import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "build34_phase_clock",
    Path(__file__).resolve().parents[1]/"tools/build34_startup_phase_clock.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class PhaseClockTests(unittest.TestCase):
    def clock(self, sink, **kwargs):
        ticks = iter(range(0, 10000, 10))
        cpu = iter(range(0, 10000, 2))
        return m.PhaseClock(sink, wall_ns=lambda: next(ticks),
                            cpu_ns=lambda: next(cpu), **kwargs)

    def test_same_arguments_and_exact_return_identity(self):
        records = []
        clock = self.clock(records.append)
        value = object()
        def action(first, *, second):
            self.assertEqual((first, second), (1, 2))
            return value
        self.assertIs(clock.call("protected", action, 1, second=2), value)
        self.assertEqual(records, [dict(sequence=1, parent_sequence=None,
                                       phase="protected", elapsed_ns=10,
                                       start_monotonic_ns=0, end_monotonic_ns=10,
                                       process_cpu_ns=2, status="returned")])

    def test_exact_original_exception_preserved(self):
        records = []
        clock = self.clock(records.append)
        failure = ValueError("private failure details")
        def fail():
            raise failure
        with self.assertRaises(ValueError) as caught:
            clock.call("policy", fail)
        self.assertIs(caught.exception, failure)
        self.assertEqual(records[0]["status"], "error")
        self.assertEqual(records[0]["error_type"], "ValueError")
        self.assertNotIn("private failure details", repr(records))

    def test_original_failure_survives_a_failed_sink(self):
        def sink(record):
            raise OSError("sink failed")
        failure = RuntimeError("validator failed")
        def fail():
            raise failure
        with self.assertRaises(RuntimeError) as caught:
            self.clock(sink).call("policy", fail)
        self.assertIs(caught.exception, failure)

    def test_sink_failure_cannot_be_counted_as_a_successful_measurement(self):
        def sink(record):
            raise OSError("sink failed")
        with self.assertRaisesRegex(OSError, "sink failed"):
            self.clock(sink).call("policy", lambda: 1)

    def test_clock_failure_cannot_mask_the_original_exception_or_leave_parentage(self):
        ticks = iter((1,))
        clock = m.PhaseClock(lambda record: None, wall_ns=lambda: next(ticks), cpu_ns=lambda: 1)
        failure = RuntimeError("actual failure")
        def fail():
            raise failure
        with self.assertRaises(RuntimeError) as caught:
            clock.call("policy", fail)
        self.assertIs(caught.exception, failure)
        self.assertEqual(clock.stack, [])

    def test_nested_intervals_have_parentage_and_must_not_be_added(self):
        records = []
        clock = self.clock(records.append)
        self.assertEqual(clock.call("build", lambda: clock.call("policy", lambda: 7)), 7)
        self.assertEqual([row["sequence"] for row in records], [2, 1])
        self.assertEqual([row["parent_sequence"] for row in records], [1, None])
        self.assertEqual([row["elapsed_ns"] for row in records], [10, 30])
        self.assertEqual(clock.stack, [])

    def test_record_budget_never_skips_the_underlying_actions(self):
        records = []
        calls = []
        clock = self.clock(records.append, limit=2)
        for index in range(5):
            self.assertEqual(clock.call("check", lambda: calls.append(index) or index), index)
        self.assertEqual(calls, list(range(5)))
        self.assertEqual(len(records), 2)
        self.assertEqual(clock.stack, [])

    def test_exception_after_budget_exhaustion_still_propagates(self):
        clock = self.clock(lambda record: None, limit=1)
        clock.call("first", lambda: None)
        with self.assertRaisesRegex(ValueError, "still checked"):
            clock.call("second", lambda: (_ for _ in ()).throw(ValueError("still checked")))

    def test_untrusted_phase_labels_do_not_run_an_action(self):
        calls = []
        clock = self.clock(lambda record: None)
        for label in ("/private/path", "has spaces", "x"*65, "", None):
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    clock.call(label, lambda: calls.append(label))
        self.assertEqual(calls, [])

    def test_invalid_limits(self):
        for limit in (0, -1, 1025, True, 1.5):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    self.clock(lambda record: None, limit=limit)

    def test_wrapping_preserves_name_and_calls_once(self):
        records = []
        calls = []
        def actual(value):
            calls.append(value)
            return value
        observed = self.clock(records.append).wrap("actual", actual)
        self.assertEqual(observed.__name__, actual.__name__)
        self.assertIs(observed.__wrapped__, actual)
        self.assertEqual(observed(5), 5)
        self.assertEqual(calls, [5])


if __name__ == "__main__":
    unittest.main()
