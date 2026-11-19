#!/usr/bin/env python3
"""CPU-only ordering, fixed-deadline and fail-closed candidate tests."""

import importlib.util
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "build34_startup_preflight",
    Path(__file__).resolve().parents[1] / "tools/build34_startup_preflight.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.events = []
        self.ready_at = 100.0
        self.failure = None
        self.callbacks = dict(installed_checks=self.installed,
                              verify_disk=self.disk,
                              guardian_ready=self.ready,
                              validate_guardian=self.validate,
                              guard=self.guard,
                              monotonic=lambda: self.now,
                              sleep=self.sleep)

    def guard(self):
        self.events.append("guard")
        if self.failure is not None:
            raise self.failure

    def installed(self):
        self.events.append("installed")
        self.now += 2.0

    def disk(self):
        self.events.append("EFI")
        self.now += 1.0

    def ready(self):
        self.events.append("ready")
        return self.now >= self.ready_at

    def validate(self):
        self.events.append("receipt-and-PID")

    def sleep(self, seconds):
        self.assertGreater(seconds, 0)
        self.assertLessEqual(seconds, m.POLL_SECONDS)
        self.events.append("sleep")
        self.now += seconds

    def run_candidate(self, **overrides):
        return m.preflight_before_guardian(**dict(self.callbacks, **overrides))

    def test_complete_checks_run_once_even_if_already_ready(self):
        self.assertIsNone(self.run_candidate())
        self.assertEqual([x for x in self.events if x != "guard"],
                         ["installed", "EFI", "ready", "receipt-and-PID"])

    def test_pending_guardian_does_not_delay_full_preflight(self):
        self.ready_at = 104.0
        self.run_candidate()
        self.assertLess(self.events.index("EFI"), self.events.index("sleep"))
        self.assertEqual(self.events.count("installed"), 1)
        self.assertEqual(self.events.count("EFI"), 1)
        self.assertEqual(self.events.count("receipt-and-PID"), 1)

    def test_missing_guardian_cannot_pass_or_extend_deadline(self):
        self.ready_at = float("inf")
        with self.assertRaises(TimeoutError):
            self.run_candidate()
        self.assertEqual(self.now, 145.0)
        self.assertNotIn("receipt-and-PID", self.events)

    def test_slow_full_preflight_uses_the_original_deadline(self):
        def slow():
            self.events.append("installed")
            self.now += 46.0
        with self.assertRaises(TimeoutError):
            self.run_candidate(installed_checks=slow)
        self.assertNotIn("EFI", self.events)
        self.assertNotIn("receipt-and-PID", self.events)

    def test_ready_after_slow_disk_check_does_not_bypass_deadline(self):
        def slow_disk():
            self.events.append("EFI")
            self.now = 145.0
        with self.assertRaises(TimeoutError):
            self.run_candidate(verify_disk=slow_disk)
        self.assertNotIn("receipt-and-PID", self.events)

    def test_ready_callback_cannot_extend_deadline(self):
        def late_ready():
            self.now = 145.0
            return True
        with self.assertRaises(TimeoutError):
            self.run_candidate(guardian_ready=late_ready)
        self.assertNotIn("receipt-and-PID", self.events)

    def test_receipt_validation_is_also_inside_the_deadline(self):
        def slow_receipt():
            self.events.append("receipt-and-PID")
            self.now = 145.0
        with self.assertRaises(TimeoutError):
            self.run_candidate(validate_guardian=slow_receipt)

    def test_initial_failure_stops_before_any_expensive_work(self):
        failure = RuntimeError("recovery pending")
        self.failure = failure
        with self.assertRaises(RuntimeError) as caught:
            self.run_candidate()
        self.assertIs(caught.exception, failure)
        self.assertEqual(self.events, ["guard"])

    def test_all_callback_failures_propagate_without_retry(self):
        for name in self.callbacks:
            if name == "monotonic":
                continue
            with self.subTest(callback=name):
                self.setUp()
                self.ready_at = 110.0
                failure = OSError(name)
                calls = []
                def fail():
                    calls.append(name)
                    raise failure
                def fail_sleep(_):
                    fail()
                with self.assertRaises(OSError) as caught:
                    self.run_candidate(**{name: fail_sleep if name == "sleep" else fail})
                self.assertIs(caught.exception, failure)
                self.assertEqual(calls, [name])

    def test_recovery_during_either_validator_is_not_admitted(self):
        for name in ("installed_checks", "verify_disk"):
            with self.subTest(callback=name):
                self.setUp()
                failure = RuntimeError("recovery started")
                def changed():
                    self.failure = failure
                with self.assertRaises(RuntimeError) as caught:
                    self.run_candidate(**{name: changed})
                self.assertIs(caught.exception, failure)
                self.assertNotIn("receipt-and-PID", self.events)

    def test_recovery_while_waiting_is_not_admitted(self):
        self.ready_at = 110.0
        def changed(_):
            self.failure = RuntimeError("guardian failed")
        with self.assertRaisesRegex(RuntimeError, "guardian failed"):
            self.run_candidate(sleep=changed)
        self.assertNotIn("receipt-and-PID", self.events)

    def test_recovery_as_readiness_appears_is_not_admitted(self):
        def changed():
            self.failure = RuntimeError("live jobs changed")
            return True
        with self.assertRaisesRegex(RuntimeError, "live jobs changed"):
            self.run_candidate(guardian_ready=changed)
        self.assertNotIn("receipt-and-PID", self.events)

    def test_recovery_during_receipt_validation_is_not_admitted(self):
        def changed():
            self.failure = RuntimeError("recovery started")
        with self.assertRaisesRegex(RuntimeError, "recovery started"):
            self.run_candidate(validate_guardian=changed)

    def test_stale_or_wrong_receipt_and_dead_or_nonroot_PID_are_rejected(self):
        for reason in ("wrong boot", "stale receipt", "dead PID", "nonroot PID",
                       "wrong command", "wrong action"):
            with self.subTest(reason=reason):
                self.setUp()
                failure = AssertionError(reason)
                def reject():
                    raise failure
                with self.assertRaises(AssertionError) as caught:
                    self.run_candidate(validate_guardian=reject)
                self.assertIs(caught.exception, failure)

    def test_truthy_unknown_readiness_does_not_pass(self):
        for ready in (1, "ready", object(), None):
            with self.subTest(ready=ready):
                self.setUp()
                with self.assertRaises(TypeError):
                    self.run_candidate(guardian_ready=lambda: ready)
                self.assertNotIn("receipt-and-PID", self.events)

    def test_invalid_or_backwards_clock_does_not_pass(self):
        for ticks in ((float("nan"),), (float("inf"),),
                      (100.0, float("nan")), (100.0, 99.0)):
            with self.subTest(ticks=ticks):
                iterator = iter(ticks)
                with self.assertRaises(ValueError):
                    self.run_candidate(monotonic=lambda: next(iterator))

    def test_clock_failure_keeps_exact_exception(self):
        failure = OSError("clock failed")
        def fail():
            raise failure
        with self.assertRaises(OSError) as caught:
            self.run_candidate(monotonic=fail)
        self.assertIs(caught.exception, failure)

    def test_wait_and_deadline_constants_are_fixed(self):
        self.assertEqual(m.READINESS_SECONDS, 45.0)
        self.assertEqual(m.POLL_SECONDS, 0.1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
