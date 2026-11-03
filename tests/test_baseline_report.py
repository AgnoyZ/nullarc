"""Exercise the phase-1 verdict tool: thresholds, refusals and the honesty of a synthetic capture.

Every capture in this file is synthetic -- written to say what the tool does with a shape of input, not to
claim any hardware measurement. The tool stamps such a report as not-evidence, and one case checks that.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/phx_baseline_report.py"

KNOBS = {
    "debug.phxfb_alias": 1, "debug.phxfb_vbl_staged": 1, "debug.nvaccel_iop": 1,
    "debug.nvaccel_iop_sse": 1, "debug.nvaccel_iop_vsync": 1, "debug.nvaccel_vm_sticky": 1,
    "debug.phxbos_flush": 0,
}


def window(index, **overrides):
    """One measured window: 120 Hz panel, frames reaching the panel, one refresh's worth of microseconds."""
    record = {
        "index": index, "vbl_ticks": 7200, "vbl_hz": 120.0, "frames_on_panel": 7200, "presents_per_s": 120.0,
        "avg_copy_us": 400.0, "copy_share_of_refresh_pct": 4.8, "copy_skip": 0, "blank_frames": 0,
        "iop_fail": 0, "vbl_late_avg_us": 60.0, "vbl_late_max_us": 300.0,
        "iop_gap1": 7100, "iop_gap2": 80, "iop_gap3": 15, "iop_gap4": 5,
        "iop_vsync_waits": 200, "iop_vsync_late": 0,
    }
    record.update(overrides)
    return record


def capture(*windows, fixture=True, window_seconds=60, claims=None, tool="phx_baseline"):
    return {
        "tool": tool,
        "fixture": fixture,
        "host": "Darwin-x86_64",
        "window_seconds": window_seconds,
        "samples": len(windows),
        "knobs": dict(KNOBS),
        "windows": list(windows),
        "claims": claims or {"display_path_counters_read": True, "gpu_work_submitted": False,
                             "hardware_execution_established": False},
        "limitation": "synthetic, written by tests/test_baseline_report.py",
    }


class ReportTests(unittest.TestCase):
    def write(self, directory, name, record):
        path = Path(directory) / name
        path.write_text(json.dumps(record), encoding="utf-8")
        return path

    def run_tool(self, *arguments):
        return subprocess.run([sys.executable, str(TOOL), *arguments], capture_output=True, text=True, timeout=300)

    def verdict(self, *paths):
        result = self.run_tool(*[str(path) for path in paths], "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_a_copy_limited_capture_supports_h1(self):
        with tempfile.TemporaryDirectory() as temporary:
            # 8 ms of copy per frame at 120 Hz: nearly a whole refresh per frame, 50 presents a second.
            slow = capture(window(1, frames_on_panel=3000, presents_per_s=50.0, avg_copy_us=8000.0,
                                  copy_share_of_refresh_pct=96.0, iop_gap1=2400, iop_gap2=400,
                                  iop_gap3=120, iop_gap4=80),
                           window(2, frames_on_panel=3060, presents_per_s=51.0, avg_copy_us=7900.0,
                                  copy_share_of_refresh_pct=94.8, iop_gap1=2450, iop_gap2=380,
                                  iop_gap3=110, iop_gap4=120))
            report = self.verdict(self.write(temporary, "slow.json", slow))
            verdict = report["captures"][0]
            # H1 is the one that changes what gets implemented; the cadence also degrades at 50 presents/s.
            self.assertIn("H1", verdict["supported"])
            self.assertIn("H3", verdict["supported"])
            self.assertEqual(verdict["undecidable"], [])
            self.assertEqual({item["id"]: item["state"] for item in verdict["decisions"]}["H2"], "refuted")
            self.assertIn("optimise the copy", verdict["next_step"])
            self.assertAlmostEqual(verdict["metrics"]["copy_share_of_refresh_pct"], 95.4, places=1)

    def test_a_healthy_capture_supports_nothing_and_says_where_to_look_next(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = self.verdict(self.write(temporary, "healthy.json", capture(window(1), window(2))))
            verdict = report["captures"][0]
            self.assertEqual(verdict["supported"], [])
            self.assertEqual(verdict["candidates"], [])
            self.assertEqual(verdict["undecidable"], [])
            self.assertIn("application-side cost", verdict["next_step"])

    def test_a_capture_without_the_cadence_counters_cannot_decide_h3(self):
        with tempfile.TemporaryDirectory() as temporary:
            older = capture(window(1), window(2))
            for measured in older["windows"]:
                for field in ("iop_gap1", "iop_gap2", "iop_gap3", "iop_gap4", "iop_vsync_waits", "iop_vsync_late"):
                    del measured[field]
            report = self.verdict(self.write(temporary, "older.json", older))
            verdict = report["captures"][0]
            self.assertEqual(verdict["undecidable"], ["H3"])
            states = {item["id"]: item["state"] for item in verdict["decisions"]}
            self.assertEqual(states["H3"], "undecidable")
            self.assertIn("phx_baseline.sh", verdict["next_step"])
            self.assertIn("second capture", verdict["next_step"])

    def test_frames_presented_faster_than_the_panel_ticks_support_the_pacing_hypothesis(self):
        with tempfile.TemporaryDirectory() as temporary:
            doubled = capture(window(1, presents_per_s=140.0, frames_on_panel=8400, vbl_hz=120.0),
                              window(2, presents_per_s=142.0, frames_on_panel=8520, vbl_hz=120.0))
            verdict = self.verdict(self.write(temporary, "doubled.json", doubled))["captures"][0]
            self.assertIn("H3", verdict["supported"])
            self.assertIn("debug.nvaccel_iop_vsync", verdict["next_step"])

    def test_frames_landing_two_refreshes_apart_support_the_pacing_hypothesis(self):
        with tempfile.TemporaryDirectory() as temporary:
            uneven = capture(window(1, iop_gap1=1000, iop_gap2=600, iop_gap3=300, iop_gap4=100),
                             window(2, iop_gap1=1040, iop_gap2=580, iop_gap3=280, iop_gap4=110))
            verdict = self.verdict(self.write(temporary, "uneven.json", uneven))["captures"][0]
            self.assertIn("H3", verdict["supported"])
            self.assertGreater(verdict["cadence"]["dropped_refresh_pct"], 5.0)

    def test_held_back_frames_support_the_readiness_hypothesis(self):
        with tempfile.TemporaryDirectory() as temporary:
            stalled = capture(window(1, copy_skip=300, frames_on_panel=7000),
                              window(2, copy_skip=320, frames_on_panel=7010))
            verdict = self.verdict(self.write(temporary, "stalled.json", stalled))["captures"][0]
            self.assertIn("H4", verdict["supported"])
            self.assertIn("readiness", verdict["next_step"])

    def test_late_ticks_are_a_candidate_that_needs_the_ab(self):
        with tempfile.TemporaryDirectory() as temporary:
            late = capture(window(1, vbl_late_avg_us=800.0, vbl_late_max_us=3500.0),
                           window(2, vbl_late_avg_us=820.0, vbl_late_max_us=3600.0))
            verdict = self.verdict(self.write(temporary, "late.json", late))["captures"][0]
            states = {item["id"]: item["state"] for item in verdict["decisions"]}
            self.assertEqual(states["H2"], "candidate")
            self.assertEqual(verdict["candidates"], ["H2"])
            self.assertIn("B2", verdict["next_step"])

    def test_a_snapshot_capture_is_refused_not_guessed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write(temporary, "snapshot.json",
                              capture({"index": 1, "snapshot_only": True}, window_seconds=0))
            result = self.run_tool(str(path))
            self.assertEqual(result.returncode, 4)
            self.assertIn("--window 60", result.stderr)

    def test_an_incomplete_capture_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            broken = capture(window(1))
            del broken["windows"][0]["avg_copy_us"]
            result = self.run_tool(str(self.write(temporary, "broken.json", broken)))
            self.assertEqual(result.returncode, 4)
            self.assertIn("avg_copy_us", result.stderr)

    def test_a_record_that_claims_hardware_execution_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            claiming = capture(window(1), claims={"display_path_counters_read": True,
                                                  "hardware_execution_established": True})
            result = self.run_tool(str(self.write(temporary, "claiming.json", claiming)))
            self.assertEqual(result.returncode, 4)
            self.assertIn("hardware execution", result.stderr)

    def test_something_that_is_not_a_phx_baseline_record_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_tool(str(self.write(temporary, "other.json", capture(window(1), tool="other"))))
            self.assertEqual(result.returncode, 4)
            self.assertIn("phx_baseline", result.stderr)

    def test_a_synthetic_capture_is_never_called_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "verdict"
            result = self.run_tool(f"demo={self.write(temporary, 'fixture.json', capture(window(1), window(2)))}",
                                   "--out", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Synthetic input", result.stdout)
            report = json.loads((out / "verdict.json").read_text(encoding="utf-8"))
            self.assertFalse(report["evidence"])
            self.assertFalse(report["claims"]["hardware_execution_established"])
            self.assertIn("Synthetic input", (out / "verdict.md").read_text(encoding="utf-8"))

    def test_a_real_capture_is_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = self.verdict(self.write(temporary, "real.json", capture(window(1), window(2), fixture=False)))
            self.assertTrue(report["evidence"])

    def test_the_ab_comparison_reports_the_change_and_its_noise(self):
        with tempfile.TemporaryDirectory() as temporary:
            baseline = self.write(temporary, "baseline.json", capture(window(1), window(2)))
            faster = self.write(temporary, "sse.json",
                                capture(window(1, presents_per_s=90.0, frames_on_panel=5400, avg_copy_us=4000.0,
                                              copy_share_of_refresh_pct=48.0),
                                        window(2, presents_per_s=92.0, frames_on_panel=5520, avg_copy_us=3950.0,
                                              copy_share_of_refresh_pct=47.4)))
            report = self.verdict(f"baseline={baseline}", f"b1={faster}")
            comparison = report["comparisons"][0]
            rows = {row["metric"]: row for row in comparison["rows"]}
            self.assertEqual(rows["presents_per_s"]["baseline"], 120.0)
            self.assertEqual(rows["presents_per_s"]["ab"], 91.0)
            self.assertTrue(rows["presents_per_s"]["meaningful"])
            self.assertFalse(rows["vbl_late_avg_us"]["meaningful"])
            self.assertIn("single sample", comparison["note"])

    def test_a_directory_capture_and_an_output_directory_are_both_accepted_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "capture"
            directory.mkdir()
            self.write(directory, "baseline.json", capture(window(1), window(2)))
            out = Path(temporary) / "verdict"
            first = self.run_tool(f"baseline={directory}", "--out", str(out))
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue((out / "verdict.md").is_file())
            second = self.run_tool(f"baseline={directory}", "--out", str(out))
            self.assertEqual(second.returncode, 4)
            self.assertIn("exists", second.stderr)

    def test_the_demo_mode_runs_the_whole_pipeline_without_hardware(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "demo"
            result = self.run_tool("--demo", "--out", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((out / "capture-fixture.json").read_text(encoding="utf-8"))
            self.assertTrue(record["fixture"])
            self.assertIn("SYNTHETIC", record["limitation"])
            report = json.loads((out / "verdict.json").read_text(encoding="utf-8"))
            self.assertFalse(report["evidence"])
            self.assertEqual(report["captures"][0]["label"], "demo")


if __name__ == "__main__":
    unittest.main()
