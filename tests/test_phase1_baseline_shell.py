"""Exercise the real phase-1 baseline script: read-only, deltas, and its refusals.

Runs in Linux CI. Windows does not claim POSIX shell execution, so the class is skipped there, as
tests/test_boot_gate_shell.py does.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/phx_baseline.sh"

KNOBS = {
    "debug.phxfb_alias": 1, "debug.phxfb_vbl_staged": 1, "debug.nvaccel_iop": 1,
    "debug.nvaccel_iop_sse": 1, "debug.nvaccel_iop_vsync": 1, "debug.nvaccel_vm_sticky": 1,
    "debug.phxbos_flush": 0,
}
COUNTERS = {
    "debug.phxfb_vbl_n": 120, "debug.phxfb_vbl_late_us_sum": 12000, "debug.phxfb_vbl_late_us_max": 350,
    "debug.nvaccel_iop_ok": 120, "debug.nvaccel_iop_ok_h0": 120, "debug.nvaccel_iop_src_res": 0,
    "debug.nvaccel_iop_src_surf": 120, "debug.nvaccel_iop_copy_skip": 0, "debug.nvaccel_iop_blank": 0,
    "debug.nvaccel_iop_fail": 0, "debug.nvaccel_iop_copy_us": 2000, "debug.nvaccel_iop_copy_us_max": 2600,
    "debug.nvaccel_iop_copy_us_sum": 240000, "debug.nvaccel_vm_parked": 0, "debug.nvaccel_vm_unparked": 0,
    "debug.nvaccel_iop_gap1": 100, "debug.nvaccel_iop_gap2": 15, "debug.nvaccel_iop_gap3": 4,
    "debug.nvaccel_iop_gap4": 1, "debug.nvaccel_iop_vsync_waits": 8, "debug.nvaccel_iop_vsync_late": 1,
    "debug.phxbos_handles_high": 3800, "debug.phxbos_handles_full": 0,
}

FAKE_SYSCTL = '''#!{python}
import json, os, pathlib, sys
state = pathlib.Path(os.environ["PHX_FAKE_STATE"])
args = sys.argv[1:]
with open(state / "calls.jsonl", "a", encoding="utf-8") as f:
    f.write(json.dumps(args) + "\\n")
if "-w" in args:
    sys.exit("this script must never write a sysctl")
if len(args) != 2 or args[0] != "-n":
    sys.exit(2)
name = args[1]
if name == os.environ.get("PHX_FAKE_MISSING"):
    sys.exit(1)
knobs = {knobs!r}
counters = {counters!r}
tickfile = state / "tick"
if name in knobs:
    print(knobs[name])
    sys.exit(0)
if name not in counters:
    sys.exit(1)
# One sample per pass: the script reads its counters in a fixed order, VBL first.
tick = int(tickfile.read_text()) if tickfile.exists() else 0
print(counters[name] * tick if name != "debug.phxfb_vbl_late_us_max" and name != "debug.nvaccel_iop_copy_us" and name != "debug.nvaccel_iop_copy_us_max" else counters[name])
if name == "debug.phxfb_vbl_n":
    tickfile.write_text(str(tick + 1))
'''

FAKE_IOREG = '''#!{python}
import sys
sys.exit(0)
'''

FAKE_UNAME = '''#!{python}
import os, sys
if "-m" in sys.argv[1:]:
    print("arm64" if os.environ.get("PHX_FAKE_ARCH") == "arm64" else "x86_64")
else:
    print("Linux" if os.environ.get("PHX_FAKE_OS") == "linux" else "Darwin")
'''


@unittest.skipIf(os.name == "nt", "POSIX shell execution runs in Linux CI; Windows does not claim it")
class BaselineTests(unittest.TestCase):
    def fixture(self, directory, *, missing=None, host="darwin"):
        work = Path(directory)
        bindir = work / "bin"
        bindir.mkdir()
        state = work / "state"
        state.mkdir()
        scripts = {
            "sysctl": FAKE_SYSCTL.format(python=sys.executable, knobs=KNOBS, counters=COUNTERS),
            "ioreg": FAKE_IOREG.format(python=sys.executable),
            "uname": FAKE_UNAME.format(python=sys.executable),
        }
        for name, text in scripts.items():
            path = bindir / name
            path.write_text(text, encoding="utf-8")
            path.chmod(0o700)
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "TMPDIR": str(work),
               "PHX_FAKE_STATE": str(state), "PHX_FAKE_OS": host,
               "PHX_SYSCTL": str(bindir / "sysctl"), "PHX_IOREG": str(bindir / "ioreg"),
               "PHX_UNAME": str(bindir / "uname")}
        if missing:
            env["PHX_FAKE_MISSING"] = missing
        return work, state, env

    def run_script(self, env, *args):
        return subprocess.run(["/bin/sh", str(SCRIPT), *args], capture_output=True, text=True,
                              timeout=120, env=env)

    def test_window_reports_rates_and_deltas(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, state, env = self.fixture(temporary)
            out = work / "baseline"
            result = self.run_script(env, "--out", str(out), "--window", "1")
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads((out / "baseline.json").read_text())
            window = record["windows"][0]
            # 120 ticks in one second on a 120 Hz panel, 120 frames, 2.0 ms each: a quarter of a refresh.
            self.assertAlmostEqual(window["vbl_hz"], 120.0, places=1)
            self.assertEqual(window["frames_on_panel"], 120)
            self.assertAlmostEqual(window["presents_per_s"], 120.0, places=1)
            self.assertAlmostEqual(window["avg_copy_us"], 2000.0, places=1)
            self.assertAlmostEqual(window["copy_share_of_refresh_pct"], 24.0, places=1)
            self.assertAlmostEqual(window["vbl_late_avg_us"], 100.0, places=1)
            self.assertEqual(window["vbl_late_max_us"], 350)
            # The present cadence H3 is decided from (docs/analysis.md §5): the deltas reach the record...
            self.assertEqual(window["iop_gap1"], 100)
            self.assertEqual(window["iop_gap2"], 15)
            self.assertEqual(window["iop_gap3"], 4)
            self.assertEqual(window["iop_gap4"], 1)
            self.assertEqual(window["iop_vsync_waits"], 8)
            self.assertEqual(window["iop_vsync_late"], 1)
            self.assertEqual(record["knobs"]["debug.nvaccel_iop_sse"], 1)
            self.assertEqual(record["claims"], {"display_path_counters_read": True, "gpu_work_submitted": False,
                                                "hardware_execution_established": False})
            # ...and the summary shows them, so a session can be read without opening the JSON.
            summary = (out / "summary.txt").read_text()
            self.assertTrue(summary.strip())
            self.assertIn("cadence", summary)
            self.assertIn("vsync_late", summary)
            calls = [json.loads(line) for line in (state / "calls.jsonl").read_text().splitlines()]
            self.assertTrue(calls)
            self.assertFalse([c for c in calls if "-w" in c], "the baseline tool must never write a sysctl")
            self.assertTrue(all(c[0] == "-n" for c in calls), calls)

    def test_snapshot_mode_has_no_rate(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, _, env = self.fixture(temporary)
            out = work / "snapshot"
            result = self.run_script(env, "--out", str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            window = json.loads((out / "baseline.json").read_text())["windows"][0]
            self.assertTrue(window["snapshot_only"])
            self.assertNotIn("copy_share_of_refresh_pct", window)
            self.assertIn("snapshot only", (out / "summary.txt").read_text())

    def test_refuses_a_non_darwin_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, _, env = self.fixture(temporary, host="linux")
            result = self.run_script(env, "--out", str(work / "baseline"))
            self.assertEqual(result.returncode, 3)
            self.assertFalse((work / "baseline").exists())

    def test_refuses_an_existing_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, _, env = self.fixture(temporary)
            out = work / "taken"
            out.mkdir()
            result = self.run_script(env, "--out", str(out))
            self.assertEqual(result.returncode, 4)
            self.assertEqual(list(out.iterdir()), [])

    def test_a_missing_counter_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, _, env = self.fixture(temporary, missing="debug.nvaccel_iop_copy_us_max")
            out = work / "baseline"
            result = self.run_script(env, "--out", str(out), "--window", "1")
            self.assertEqual(result.returncode, 5)
            self.assertIn("debug.nvaccel_iop_copy_us_max", result.stderr)

    def test_usage_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, _, env = self.fixture(temporary)
            self.assertEqual(self.run_script(env).returncode, 2)
            self.assertEqual(self.run_script(env, "--out", str(work / "b"), "--window", "x").returncode, 2)
            self.assertEqual(self.run_script(env, "--out", str(work / "b"), "--samples", "0").returncode, 2)


if __name__ == "__main__":
    unittest.main()
