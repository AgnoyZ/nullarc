"""Original build-34 readback semantics and desktop evidence; CPU fixtures only."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "desktop_evidence", ROOT / "tools/upstream34_layout/desktop_evidence.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DesktopEvidenceTests(unittest.TestCase):
    def samples(self):
        before = {"debug.nvaccel_iop_ok": 616, "WindowServer_pids": ["fixture"],
                  "debug.phxagdc": 1, "debug.nvaccelfb": 1,
                  "debug.nvaccel_iop": 1, "debug.phxfb_hold": 0}
        return before, dict(before, **{"debug.nvaccel_iop_ok": 630})

    def test_original_boolean_readback_with_progress_passes(self):
        before, after = self.samples()
        MODULE.validate_frames(before, after, [], [])

    def test_write_command_three_is_not_a_readback_value(self):
        before, after = self.samples()
        self.assertNotEqual(3, after["debug.nvaccelfb"])
        after["debug.nvaccelfb"] = 3
        with self.assertRaisesRegex(AssertionError, "after debug.nvaccelfb: expected 1, got 3"):
            MODULE.validate_frames(before, after, [], [])

    def test_no_progress_regression_and_negative_counter_are_refused(self):
        for start, end in [(616, 616), (616, 615), (-1, 10)]:
            before, after = self.samples()
            before["debug.nvaccel_iop_ok"] = start
            after["debug.nvaccel_iop_ok"] = end
            with self.assertRaisesRegex(AssertionError, "no measured frame progress"):
                MODULE.validate_frames(before, after, [], [])

    def test_restart_absence_or_multiple_compositors_are_refused(self):
        for pids in [[], ["other"], ["fixture", "other"]]:
            before, after = self.samples()
            after["WindowServer_pids"] = pids
            with self.assertRaisesRegex(AssertionError, "WindowServer changed"):
                MODULE.validate_frames(before, after, [], [])

    def test_both_samples_require_all_original_display_gates(self):
        for which in [0, 1]:
            for name, value in [("debug.phxagdc", 0), ("debug.nvaccelfb", 0),
                                ("debug.nvaccel_iop", 0), ("debug.phxfb_hold", 1)]:
                samples = self.samples()
                samples[which][name] = value
                with self.subTest(sample=which, gate=name):
                    with self.assertRaisesRegex(AssertionError, name):
                        MODULE.validate_frames(*samples, [], [])

    def test_new_report_is_not_hidden_by_successful_frames(self):
        with self.assertRaisesRegex(AssertionError, "new WindowServer diagnostic report"):
            MODULE.validate_frames(*self.samples(), [], ["fixture-report"])

    def test_historical_report_set_can_remain_unchanged(self):
        MODULE.validate_frames(*self.samples(), ["old-report"], ["old-report"])

    def test_boolean_or_text_values_do_not_pass_integer_gates(self):
        for name, value in [("debug.nvaccelfb", True), ("debug.nvaccel_iop_ok", "630")]:
            before, after = self.samples()
            after[name] = value
            with self.assertRaises(AssertionError):
                MODULE.validate_frames(before, after, [], [])

    def test_checker_does_not_mutate_samples_or_reports(self):
        before, after = self.samples()
        saved = dict(before), dict(after)
        reports = ["old-report"]
        MODULE.validate_frames(before, after, reports, reports)
        self.assertEqual(saved, (before, after))
        self.assertEqual(["old-report"], reports)


if __name__ == "__main__":
    unittest.main(verbosity=2)
