"""Actual upstream entrypoints and shell order under synthetic IOKit/process fixtures only."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("upstream34_build", ROOT / "tools/upstream34_layout/build.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class Upstream34LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temp.name)
        cls.source, cls.record = BUILD.materialize(cls.work / "candidate")
        cls.binaries = {}
        for name in ["mesboot", "phxctl"]:
            for flavor in ["old", "new"]:
                source = cls.source / (name + ".c")
                if flavor == "old":
                    source = cls.source / (name + "-original.c")
                    source.write_bytes(BUILD.run(["git", "show", BUILD.UPSTREAM + ":tools/phxctl/" + name + ".c"], cwd=ROOT))
                binary = cls.work / (flavor + "-" + name)
                BUILD.run(["/usr/bin/xcrun", "clang", "-O1", "-g", "-Wall", "-Wextra",
                           "-mmacosx-version-min=12.0", "-fsanitize=address,undefined",
                           "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
                           '-DPHX34_SOURCE="' + str(source) + '"',
                           str(ROOT / "tests/fixtures/upstream34_fake_iokit.c"),
                           "-framework", "CoreFoundation", "-o", str(binary)])
                linked = BUILD.run(["/usr/bin/otool", "-L", str(binary)]).decode()
                if "IOKit.framework" in linked:
                    raise AssertionError("CPU fixture must not link the real IOKit framework")
                cls.binaries[flavor, name] = binary

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def invoke(self, name, *args, fixture="target", flavor="new"):
        env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "PHX34_FIXTURE": fixture}
        result = subprocess.run([str(self.binaries[flavor, name]), *args], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertNotIn("Sanitizer", result.stderr)
        lines = result.stdout.splitlines()
        self.assertTrue(lines, result.stderr)
        return result, json.loads(lines[-1])

    def test_actual_original_gart_reproduces_wrong_target_mapping(self):
        result, trace = self.invoke("mesboot", "gart", flavor="old")
        self.assertEqual(0, result.returncode)
        self.assertGreater(trace["table_errors"], 0)
        self.assertFalse(trace["table_base_match"])
        self.assertFalse(trace["system_range_match"])
        self.assertFalse(trace["default_addresses_match"])

    def test_actual_corrected_gart_all_PTEs_registers_and_zero_page(self):
        result, trace = self.invoke("mesboot", "gart")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(65536, trace["table_writes"])
        self.assertEqual(1024, trace["default_writes"])
        self.assertEqual(0, trace["table_errors"])
        for key in ["first_last_PTE_match", "table_base_match", "system_range_match", "default_addresses_match"]:
            self.assertTrue(trace[key], key)

    def test_both_helpers_refuse_bad_registry_before_opening_client(self):
        fixtures = ["missing", "wrong-type", "zero", "negative", "unaligned", "overflow",
                    "small-aperture", "small-vram", "zero-size", "wrong-mc", "build39"]
        for name in ["mesboot", "phxctl"]:
            for fixture in fixtures:
                with self.subTest(helper=name, fixture=fixture):
                    result, trace = self.invoke(name, "layout", fixture=fixture)
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual(0, trace["calls"])
                    self.assertEqual(0, trace["writes"])

    def test_handshake_failure_is_terminal_before_writes(self):
        for name in ["mesboot", "phxctl"]:
            for fixture in ["hello", "hello-size"]:
                with self.subTest(helper=name, fixture=fixture):
                    result, trace = self.invoke(name, "layout", fixture=fixture)
                    self.assertIn(result.returncode, [74, 75])
                    self.assertEqual(0, trace["writes"])

    def test_layout_modes_and_reference_geometry_do_not_write(self):
        for name in ["mesboot", "phxctl"]:
            for fixture in ["target", "reference"]:
                with self.subTest(helper=name, fixture=fixture):
                    result, trace = self.invoke(name, "layout", fixture=fixture)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual(1, trace["calls"])
                    self.assertEqual(0, trace["writes"])
                    if name == "phxctl" and fixture == "target":
                        self.assertEqual("67108864 128 134217728 128 2281701376 7", result.stdout.splitlines()[0])

    def test_stale_raw_TMR_words_refused_before_firmware_call(self):
        for words in [["0x08000000", "0x80", "0x4000000", "0x2", "0x0C000000", "0x6A"],
                      ["0x08000000", "0x80", "0x4000000", "0x2", "0x80000000", "0x7"]]:
            result, trace = self.invoke("phxctl", "raw", "0x5", *words)
            self.assertEqual(75, result.returncode)
            self.assertEqual(0, trace["writes"])
        result, trace = self.invoke("phxctl", "raw", "0x5", "0x08000000", "0x80", "0x4000000", "0x2", "0x88000000", "0x7")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(1, trace["writes"])

    def test_transport_size_and_firmware_errors_are_terminal(self):
        cases = [("mesboot", ["gart"], "transport-scalar", 74),
                 ("phxctl", ["regs", "0x2004"], "transport-method", 74),
                 ("phxctl", ["regs", "0x2004"], "short-output", 74),
                 ("phxctl", ["raw", "0x20", "0x4000000", "0x80", "0x900", "0", "0", "0"], "firmware-status", 75),
                 ("phxctl", ["smu", "0x3", "0"], "SMU-status", 75)]
        for name, args, fixture, expected in cases:
            with self.subTest(fixture=fixture):
                result, _ = self.invoke(name, *args, fixture=fixture)
                self.assertEqual(expected, result.returncode, result.stderr)

    def test_short_firmware_never_submits_partial_payload(self):
        payload = self.work / "short-firmware.bin"
        payload.write_bytes(bytes(512))
        for command, extra in [("stage", []), ("loadfw", ["2"])]:
            with self.subTest(command=command):
                result, trace = self.invoke("phxctl", command, str(payload), "256", "4096", *extra, "0")
                self.assertEqual(74, result.returncode, result.stderr)
                self.assertEqual(0, trace["firmware_submits"])

    def shell_fixture(self, home, failure="", layout="67108864 128 134217728 128 2281701376 7"):
        helper = home / "gpu/phxctl"
        helper.mkdir(parents=True)
        bins = home / "bin"
        bins.mkdir()
        stub = '''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name;args=sys.argv[1:]
with open(os.environ['HOME']+'/calls','a') as f:f.write(json.dumps([name,*args])+'\\n')
fail=os.environ.get('FAIL','')
if name=='id':print('0');sys.exit(0)
if name=='killall':
 if fail=='watchdog-absent':print('No matching processes were found',file=sys.stderr);sys.exit(1)
 if fail=='watchdog-permission':print('killall: kill 123: Operation not permitted',file=sys.stderr);sys.exit(1)
 if fail=='watchdog-empty-error':sys.exit(1)
 if fail=='watchdog-other-error':print('synthetic cancellation failure',file=sys.stderr);sys.exit(70)
 if fail=='watchdog-wrong-status':print('No matching processes were found',file=sys.stderr);sys.exit(70)
 if fail=='watchdog-mixed-error':print('No matching processes were found\\nkillall: Operation not permitted',file=sys.stderr);sys.exit(1)
if name=='bash' and args and args[0].endswith('/bringup5.sh') and os.environ.get('NESTED_BRINGUP')=='1':
 os.execv('/bin/bash',['/bin/bash',*args])
if name=='phxctl' and args==['layout']:
 print(os.environ['LAYOUT']);sys.exit(75 if fail=='layout' else 0)
if name=='phxctl' and args and args[0]=='loadfw':print('loadfw synthetic')
if fail and ((name=='phxctl' and args and args[0]==fail) or (name=='bash' and args and args[0].endswith('/bringup5.sh') and fail=='bringup5') or (name=='mesboot' and args==[fail])):
 print('synthetic first initializer error',file=sys.stderr);sys.exit(75)
'''
        for name in ["phxctl", "mesboot"]:
            (helper / name).write_text(stub)
            (helper / name).chmod(0o700)
        for name in ["id", "bash", "sleep", "killall"]:
            (bins / name).write_text(stub)
            (bins / name).chmod(0o700)
        env = {"PATH": str(bins) + ":/usr/bin:/bin", "HOME": str(home), "LC_ALL": "C", "FAIL": failure, "LAYOUT": layout}
        return env

    def run_shell(self, name, failure="", layout=None, external=False, nested=False):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            kwargs = {} if layout is None else {"layout": layout}
            env = self.shell_fixture(home, failure, **kwargs)
            if nested:
                (home / "gpu/bringup5.sh").write_bytes((self.source / "bringup5.sh").read_bytes())
                env["NESTED_BRINGUP"] = "1"
            if external:
                ack = home / "watchdog.ready"
                ack.write_text("synthetic acknowledged independent deadline\n")
                env["PHX34_WATCHDOG_ACK"] = str(ack)
            args = ["kiqsched"] if name == "full.sh" else []
            result = subprocess.run(["/bin/bash", str(self.source / name), *args], env=env,
                                    capture_output=True, text=True, timeout=15)
            calls = [json.loads(line) for line in (home / "calls").read_text().splitlines()]
            return result, calls

    def test_bringup_preserves_original_firmware_and_power_order_with_correct_TMR(self):
        result, calls = self.run_shell("bringup5.sh")
        self.assertEqual(0, result.returncode, result.stderr)
        commands = [c[1:] for c in calls if c[0] == "phxctl"]
        self.assertEqual([["layout"], ["psp", "destroy"], ["psp", "create", "0x1100000"]], commands[:3])
        self.assertEqual(["raw", "0x20", "67108864", "128", "0x900", "0", "0", "0"], commands[4])
        self.assertEqual(["raw", "0x5", "134217728", "128", "0x4000000", "0x2", "2281701376", "7"], commands[5])
        self.assertEqual(17, sum(c[0] == "loadfw" for c in commands))
        self.assertEqual([["autoload"], ["smu", "0x3", "0"], ["smu", "0x2", "0"], ["smu", "0x16", "1"]], commands[-5:-1])
        result, calls = self.run_shell("bringup5.sh", external=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(any(c[0] in ["bash", "killall"] for c in calls))

    def test_bringup_refusals_cannot_continue_to_later_stages(self):
        for failure in ["layout", "psp", "stage", "raw", "loadfw", "autoload", "smu"]:
            with self.subTest(failure=failure):
                result, calls = self.run_shell("bringup5.sh", failure)
                self.assertNotEqual(0, result.returncode)
                commands = [c[1:] for c in calls if c[0] == "phxctl"]
                self.assertEqual(failure, commands[-1][0])
                if failure != "layout":
                    self.assertIn("synthetic first initializer error", result.stderr)
        for layout in ["", "1 2 3", "1 2 3 4 5 6 7", "1 2 3 4 5 bad"]:
            result, calls = self.run_shell("bringup5.sh", layout=layout)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual([["phxctl", "layout"]], [c for c in calls if c[0] == "phxctl"])
            self.assertFalse(any(c[0] == "bash" for c in calls))

    def test_full_stops_before_any_hardware_after_initializer_failure(self):
        result, calls = self.run_shell("full.sh", "bringup5")
        self.assertEqual(75, result.returncode)
        self.assertEqual(["id", "bash"], [c[0] for c in calls])
        for failure in ["gart", "mes", "kiqsched"]:
            result, calls = self.run_shell("full.sh", failure)
            self.assertEqual(75, result.returncode)
            commands = [c[1] for c in calls if c[0] == "mesboot"]
            self.assertEqual(failure, commands[-1])

    def test_full_retains_first_initializer_stderr_and_exact_failure_status(self):
        for external in [False, True]:
            with self.subTest(external_deadline=external):
                result, calls = self.run_shell("full.sh", "bringup5", external=external)
                self.assertEqual(75, result.returncode)
                self.assertIn("synthetic first initializer error", result.stderr)
                self.assertIn("bringup5.sh failed with status 75", result.stderr)
                self.assertIn("GPU queue initialization not started", result.stderr)
                self.assertEqual(["id", "bash"], [c[0] for c in calls])

    def test_transport_diagnostics_distinguish_error_from_short_output(self):
        result, _ = self.invoke("mesboot", "gart", fixture="transport-scalar")
        self.assertIn("transport/size failure: kr 0x", result.stderr)
        self.assertNotIn("kr 0x00000000", result.stderr)
        result, _ = self.invoke("phxctl", "regs", "0x2004", fixture="short-output")
        self.assertEqual(74, result.returncode)
        self.assertIn("kr 0x00000000", result.stderr)
        self.assertIn("bytes 0/4", result.stderr)
        result, _ = self.invoke("phxctl", "smu", "0x16", "1", fixture="SMU-status")
        self.assertEqual(75, result.returncode)
        self.assertIn("selector 100 ABI/firmware refusal", result.stderr)
        self.assertIn("input0 0x16, output0 0xff", result.stderr)

    def test_full_keeps_original_success_order(self):
        result, calls = self.run_shell("full.sh")
        self.assertEqual(0, result.returncode, result.stderr)
        commands = [c for c in calls if c[0] in ["phxctl", "mesboot"]]
        self.assertEqual([["phxctl", "wreg", "0xDE0", "1"],
                          ["phxctl", "wreg", "0xA802", "0"],
                          ["phxctl", "wreg", "0xA803", "0x01000000"],
                          ["mesboot", "gart"], ["mesboot", "mes"], ["mesboot", "kiqsched"]], commands)
        result, calls = self.run_shell("full.sh", external=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(any(c[0] == "killall" or c[:2] == ["bash", "-c"] for c in calls))

    def test_absent_watchdog_is_benign_and_reported_for_both_scripts(self):
        for name in ["bringup5.sh", "full.sh"]:
            with self.subTest(script=name):
                result, calls = self.run_shell(name, "watchdog-absent")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("upstream34-watchdog: no shutdown timer remains", result.stderr)
                self.assertEqual(["killall", "shutdown"], calls[-1])

    def test_cancellation_errors_remain_terminal_and_visible(self):
        cases = [("watchdog-permission", 1), ("watchdog-empty-error", 1),
                 ("watchdog-other-error", 70), ("watchdog-wrong-status", 70),
                 ("watchdog-mixed-error", 1)]
        for name in ["bringup5.sh", "full.sh"]:
            for failure, status in cases:
                with self.subTest(script=name, failure=failure):
                    result, _ = self.run_shell(name, failure)
                    self.assertEqual(status, result.returncode)
                    self.assertIn("cancellation failed with status " + str(status), result.stderr)
                    self.assertNotIn("upstream34-watchdog: no shutdown timer remains", result.stderr)

    def test_nested_initializer_absent_watchdog_reaches_original_queue_order(self):
        result, calls = self.run_shell("full.sh", "watchdog-absent", nested=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(2, result.stderr.count("upstream34-watchdog: no shutdown timer remains"))
        self.assertEqual(17, sum(c[:2] == ["phxctl", "loadfw"] for c in calls))
        self.assertEqual(["gart", "mes", "kiqsched"], [c[1] for c in calls if c[0] == "mesboot"])
        result, calls = self.run_shell("full.sh", "watchdog-permission", nested=True)
        self.assertEqual(1, result.returncode)
        self.assertIn("GPU queue initialization not started", result.stderr)
        self.assertFalse(any(c[0] == "mesboot" for c in calls))

    def test_external_watchdog_is_not_cancelled_in_absent_process_case(self):
        for name in ["bringup5.sh", "full.sh"]:
            with self.subTest(script=name):
                result, calls = self.run_shell(name, "watchdog-absent", external=True)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertFalse(any(c[0] == "killall" for c in calls))

    def test_silent_initializer_failure_has_line_and_status_diagnostic(self):
        result, _ = self.run_shell("bringup5.sh", "watchdog-empty-error")
        self.assertEqual(1, result.returncode)
        self.assertIn("cancellation failed with status 1", result.stderr)
        result, _ = self.run_shell("bringup5.sh", "autoload")
        self.assertEqual(75, result.returncode)
        self.assertRegex(result.stderr, r"upstream34-bringup: line [0-9]+ failed with status 75")


if __name__ == "__main__":
    unittest.main()
