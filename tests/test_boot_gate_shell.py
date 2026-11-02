import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/phx_boot_gate.sh"

KEXT = '''
+-o PhxBringup  <class PhxBringup>
    {
      "phx-780m-policy" = "strict-execution-v1"
      "phx-build" = 32
      "phx-fb-phys" = 553648128
      "phx-fb-aper-len" = 268435456
    }
'''


@unittest.skipIf(os.name == "nt", "POSIX shell execution runs in Linux CI; Windows does not claim it")
class BootGateTests(unittest.TestCase):
    def fixture(self, directory, fault="ok"):
        work = Path(directory)
        bindir = work / "bin"
        bindir.mkdir()
        calls = work / "calls.jsonl"
        program = f"""#!{sys.executable}
import pathlib, sys
name = pathlib.Path(sys.argv[0]).name
if name == "uname":
    if sys.argv[1] == "-s":
        print("Linux" if {fault!r} == "non-macos" else "Darwin")
    else:
        print("arm64" if {fault!r} == "arm" else "x86_64")
    sys.exit(0)
if name == "ioreg":
    if {fault!r} == "no-kext":
        sys.exit(1)
    text = {KEXT!r}
    if {fault!r} == "wrong-policy":
        text = text.replace("strict-execution-v1", "legacy")
    if {fault!r} == "wrong-build":
        text = text.replace('"phx-build" = 32', '"phx-build" = 31')
    if {fault!r} == "no-fb":
        text = text.replace('"phx-fb-phys" = 553648128', '"phx-fb-phys" = 0')
    sys.stdout.write(text)
    sys.exit(0)
sys.exit(99)
"""
        for name in ("uname", "ioreg"):
            path = bindir / name
            path.write_text(program, encoding="utf-8")
            path.chmod(0o700)
        return work, bindir, calls

    def gate(self, bindir, *args):
        env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C",
               "PHX_BOOT_GATE_TEST": "1", "PHX_UNAME": str(bindir / "uname"),
               "PHX_IOREG": str(bindir / "ioreg")}
        return subprocess.run(["/bin/sh", str(SCRIPT), *args], capture_output=True, text=True,
                              timeout=60, env=env)

    def bundle(self, directory, fault="ok", *, stages=("10-pre", "20-mes"), fail=None, hang=None):
        work, bindir, calls = self.fixture(directory, fault)
        stage_dir = work / "stages"
        stage_dir.mkdir()
        for name in stages:
            body = "exit 0"
            if name == fail:
                body = "exit 9"
            if name == hang:
                body = "/bin/sleep 5"
            path = stage_dir / name
            path.write_text(f"#!/bin/sh\nprintf '%s\\n' \"{name}\" >> {str(calls)!r}\n{body}\n", encoding="utf-8")
            path.chmod(0o700)
        release = work / "release.sh"
        release.write_text(f"#!/bin/sh\nprintf 'release\\n' >> {str(work / 'release.calls')!r}\nexit 0\n",
                           encoding="utf-8")
        release.chmod(0o700)
        return work, bindir, calls, stage_dir, release, work / "state"

    def run_gate(self, work, bindir, stage_dir, release, state, *, check=False):
        args = ["--state", str(state), "--stages", str(stage_dir), "--expected-build", "32",
                "--release", str(release), "--timeout", "1"]
        if check:
            args.append("--check")
        return self.gate(bindir, *args)

    def calls(self, path):
        return path.read_text().split() if path.exists() else []

    def test_happy_path_runs_stages_in_order_and_releases(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, bindir, calls, stage_dir, release, state = self.bundle(temporary)
            result = self.run_gate(work, bindir, stage_dir, release, state)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(["10-pre", "20-mes"], self.calls(calls))
            self.assertEqual(["release"], self.calls(work / "release.calls"))
            self.assertFalse((state / "attempt.pending").exists())
            self.assertFalse((state / "gate.lock").exists())
            self.assertEqual(0o700, stat.S_IMODE(state.stat().st_mode))
            self.assertEqual(0o600, stat.S_IMODE((state / "gate.log").stat().st_mode))
            self.assertIn("stage 20-mes: ok", (state / "gate.log").read_text())

    def test_a_failing_stage_stops_the_sequence_and_still_releases(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, bindir, calls, stage_dir, release, state = self.bundle(temporary, fail="10-pre")
            result = self.run_gate(work, bindir, stage_dir, release, state)
            self.assertEqual(77, result.returncode)
            self.assertEqual(["10-pre"], self.calls(calls))
            self.assertEqual(["release"], self.calls(work / "release.calls"))
            self.assertFalse((state / "attempt.pending").exists())
            self.assertIn("failed with status 9", (state / "gate.log").read_text())

    def test_a_hanging_stage_times_out_before_later_stages(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, bindir, calls, stage_dir, release, state = self.bundle(temporary, hang="10-pre")
            result = self.run_gate(work, bindir, stage_dir, release, state)
            self.assertEqual(78, result.returncode)
            self.assertEqual(["10-pre"], self.calls(calls))
            self.assertTrue((state / "stage-10-pre.timeout").exists())
            self.assertEqual(["release"], self.calls(work / "release.calls"))

    def test_pending_marker_from_an_unfinished_attempt_refuses_to_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, bindir, calls, stage_dir, release, state = self.bundle(temporary)
            state.mkdir()
            (state / "attempt.pending").write_text("")
            result = self.run_gate(work, bindir, stage_dir, release, state)
            self.assertEqual(76, result.returncode)
            self.assertEqual([], self.calls(calls))
            self.assertTrue((state / "attempt.pending").exists())
            self.assertEqual(["release"], self.calls(work / "release.calls"))

    def test_kill_switch_runs_nothing_but_releases(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, bindir, calls, stage_dir, release, state = self.bundle(temporary)
            state.mkdir()
            (state / "off").write_text("")
            result = self.run_gate(work, bindir, stage_dir, release, state)
            self.assertEqual(0, result.returncode)
            self.assertEqual([], self.calls(calls))
            self.assertEqual(["release"], self.calls(work / "release.calls"))

    def test_a_live_instance_holds_the_lock_and_is_not_released_by_a_second_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, bindir, calls, stage_dir, release, state = self.bundle(temporary)
            state.mkdir()
            (state / "gate.lock").mkdir()
            (state / "gate.lock" / "pid").write_text(str(os.getpid()))
            result = self.run_gate(work, bindir, stage_dir, release, state)
            self.assertEqual(75, result.returncode)
            self.assertEqual([], self.calls(calls))
            self.assertFalse((work / "release.calls").exists())
            self.assertTrue((state / "gate.lock").exists())

    def test_a_stale_lock_is_replaced_and_the_run_continues(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, bindir, calls, stage_dir, release, state = self.bundle(temporary)
            state.mkdir()
            (state / "gate.lock").mkdir()
            (state / "gate.lock" / "pid").write_text("999999")
            result = self.run_gate(work, bindir, stage_dir, release, state)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(["10-pre", "20-mes"], self.calls(calls))

    def test_host_and_kext_preconditions_refuse_before_any_stage(self):
        for fault, code in (("non-macos", 74), ("arm", 74), ("no-kext", 79),
                            ("wrong-policy", 79), ("wrong-build", 79), ("no-fb", 79)):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                work, bindir, calls, stage_dir, release, state = self.bundle(temporary, fault)
                result = self.run_gate(work, bindir, stage_dir, release, state)
                self.assertEqual(code, result.returncode, result.stderr)
                self.assertEqual([], self.calls(calls))
                self.assertFalse((work / "release.calls").exists())
                self.assertFalse((state / "attempt.pending").exists())

    def test_check_mode_writes_nothing_and_runs_nothing(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, bindir, calls, stage_dir, release, state = self.bundle(temporary)
            result = self.run_gate(work, bindir, stage_dir, release, state, check=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("stages (would run in this order): 10-pre 20-mes", result.stdout)
            self.assertIn("no stage was run and no state was written", result.stdout)
            self.assertEqual([], self.calls(calls))
            self.assertFalse(state.exists())

    def test_usage_and_stage_hygiene_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            work, bindir, calls, stage_dir, release, state = self.bundle(temporary)
            for args in (["--state", str(state), "--stages", str(stage_dir)],
                         ["--state", str(state), "--stages", str(stage_dir), "--expected-build", "x"]):
                self.assertEqual(64, self.gate(bindir, *args).returncode)
            (stage_dir / "bad name").write_text("#!/bin/sh\nexit 0\n")
            (stage_dir / "bad name").chmod(0o700)
            self.assertEqual(64, self.run_gate(work, bindir, stage_dir, release, state).returncode)
            self.assertEqual(64, self.run_gate(work, bindir, work / "missing", release, state).returncode)

    def test_the_script_has_no_reboot_nvram_or_unrelated_process_control(self):
        code = "\n".join(line for line in SCRIPT.read_text(encoding="utf-8").splitlines()
                         if not line.lstrip().startswith("#"))
        for forbidden in ("shutdown", "reboot", "nvram", "killall", "sysctl", "/Users/Shared", "Library/GPUBundles"):
            self.assertNotIn(forbidden, code)
        self.assertIn("ulimit -f 16384", code)
        self.assertIn("trap 'cleanup' 0", code)


if __name__ == "__main__":
    unittest.main()
