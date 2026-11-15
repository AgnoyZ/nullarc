"""CPU-only startup log replay, including a wall-clock adjustment regression."""
import datetime
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "startup_evidence", ROOT / "tools/upstream34_layout/startup_evidence.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StartupEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.boot_epoch = int(datetime.datetime(2026, 11, 15, 12).astimezone().timestamp())
        self.block = "2026-11-15 12:00:03 phxboot\nPhxAMDFB on the panel: 1\n"
        self.reader = MODULE.StartupLog(self.boot_epoch)

    def test_fresh_original_block_is_selected(self):
        self.assertEqual(self.block, self.reader.select("== " + self.block))

    def test_clock_step_cannot_reclassify_an_admitted_block_as_stale(self):
        text = "== " + self.block
        self.assertEqual(self.block, self.reader.select(text))
        adjusted_boundary = self.boot_epoch + 4
        self.assertEqual("", MODULE.StartupLog(adjusted_boundary).select(text))
        self.assertEqual(self.block, self.reader.select(text))
        self.assertEqual(self.boot_epoch, self.reader.boot_epoch)

    def test_complete_log_remains_visible_after_clock_step(self):
        self.reader.select("== " + self.block)
        complete = self.block + "WindowServer pid fixture, frames on the panel 10\ndone 12:01:40\n"
        self.assertEqual(complete, self.reader.select("== " + complete))

    def test_historical_block_remains_rejected(self):
        old = self.block.replace("12:00:03", "11:59:59")
        self.assertEqual("", self.reader.select("== " + old))

    def test_only_latest_block_can_supply_evidence(self):
        prior = self.block + "done 12:01:40\n"
        current = self.block.replace("12:00:03", "12:02:00")
        self.assertEqual(current, self.reader.select("== " + prior + "== " + current))

    def test_latest_invalid_header_cannot_reuse_earlier_success(self):
        text = "== " + self.block + "done 12:01:40\n== partial header"
        self.assertEqual("", self.reader.select(text))

    def test_absent_and_partial_headers_wait(self):
        for text in ["", "unrelated text", "== 2026-11-15 12:00:03 phxboot"]:
            with self.subTest(text=text):
                self.assertEqual("", self.reader.select(text))

    def test_other_boot_uses_a_separate_boundary(self):
        next_boot = MODULE.StartupLog(self.boot_epoch + 60)
        self.assertEqual("", next_boot.select("== " + self.block))
        self.assertEqual(self.block, self.reader.select("== " + self.block))

    def test_boundary_is_an_integer_read_only_snapshot(self):
        for value in [True, "1", 1.5, None]:
            with self.assertRaises(TypeError):
                MODULE.StartupLog(value)
        with self.assertRaises(AttributeError):
            self.reader.boot_epoch = self.boot_epoch + 4


if __name__ == "__main__":
    unittest.main(verbosity=2)
