"""CPU-only tests: execute rendered routers solely with synthetic helpers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from upstream34_layout import mec_runtime as runtime


def output(values=None):
    fields = {reg: 0 for reg in runtime.REGISTERS}
    fields.update({0x305D: 0xFFC, 0x305C: 0x110, 0x2004: 0xA800302C})
    fields.update(values or {})
    return "".join(f"0x{reg:05x}: 0x{fields[reg]:08x}\n" for reg in runtime.REGISTERS)


class MecRuntimeTests(unittest.TestCase):
    def test_strict_register_output_and_conservative_summary(self):
        first = runtime.parse_registers(output())
        self.assertEqual(0xFFC, first[0x305D])
        result = runtime.observation_summary([first] * 6)
        self.assertEqual(6, result["sample_count"])
        self.assertTrue(result["range_stable"])
        self.assertFalse(result["proposed_range_present_all_samples"])
        self.assertFalse(result["global_GPU_idle_established"])
        self.assertFalse(result["IB_integrity_established"])
        trial = runtime.parse_registers(output({0x305D: 0x450, 0x305C: 0, 0x2004: 0x302C}))
        result = runtime.observation_summary([trial] * 6)
        self.assertTrue(result["proposed_range_present_all_samples"])
        self.assertFalse(result["global_GPU_idle_established"])
        self.assertFalse(runtime.observation_summary([first, trial])["range_stable"])

    def test_bad_register_outputs_are_refused(self):
        original = output()
        lines = original.splitlines(keepends=True)
        bad = [None, original[:-1] + "extra\n", "".join(lines[:-1]),
               "".join(reversed(lines)), "".join([lines[0], *lines[:-1]]),
               original.replace("0x0305d:", "0x0305e:"),
               original.replace(": 0x", ": (error) 0x", 1),
               original.replace("0x00000ffc", "0xffffffff"), output({0x2004: 0}),
               "Hello failed\n" + original, original.replace("0xa800302c", "0x100000000")]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    runtime.parse_registers(value)

    def test_invalid_samples_cannot_be_promoted(self):
        valid = runtime.parse_registers(output())
        for samples in ([], [{}], [{**valid, 0x305D: True}], [{**valid, 0x305D: -1}],
                        [{**valid, 0x305D: 0xFFFFFFFF}], [{**valid, 0x2004: 0}]):
            with self.subTest(samples=samples):
                with self.assertRaises(ValueError):
                    runtime.observation_summary(samples)

    def invoke(self, policy, args, failure=""):
        with tempfile.TemporaryDirectory(prefix="original34 router '") as temp:
            packet = Path(temp)
            helper = ("#!/bin/bash\nset -euo pipefail\n"
                      "printf '%s:%s:%s:%s\\n' \"${0##*/}\" \"$1\" \"${HOME:-}\" \"${MESBOOT_MC:-}\" >> \"$TRACE\"\n"
                      "[ \"${FAIL:-}\" != \"${0##*/}\" ] || exit 75\n")
            for name in ("mesboot-original", "mesboot-control", "mesboot-mec-range"):
                path = packet / name
                path.write_text(helper)
                path.chmod(0o700)
            controller = packet / "controller.py"
            controller.write_text("import os,sys\nfrom pathlib import Path\n"
                                  "assert sys.argv[1:]==['sample-before']\n"
                                  "with Path(os.environ['TRACE']).open('a') as stream:stream.write('sample-before\\n')\n"
                                  "sys.exit(75 if os.environ.get('FAIL')=='sample-before' else 0)\n")
            router = packet / "router"
            router.write_text(runtime.render_router(packet, Path(sys.executable), controller.name, policy))
            env = {"PATH": "/usr/bin:/bin", "TRACE": str(packet / "trace"), "FAIL": failure,
                   "HOME": "synthetic-private-home", "MESBOOT_MC": "1"}
            result = subprocess.run(["/bin/bash", str(router), *args], capture_output=True, text=True,
                                    env=env, timeout=10)
            trace = (packet / "trace").read_text().splitlines() if (packet / "trace").exists() else []
            return result, trace

    def test_actual_router_preserves_original_stages_and_common_observation(self):
        for policy in runtime.POLICIES:
            for stage in ("gart", "mes", "kiqsched"):
                with self.subTest(policy=policy, stage=stage):
                    result, trace = self.invoke(policy, [stage])
                    self.assertEqual(0, result.returncode, result.stderr)
                    helper = runtime.POLICIES[policy] if stage == "kiqsched" else "mesboot-original"
                    expected = (["sample-before"] if stage == "kiqsched" else [])
                    expected += [helper + ":" + stage + ":synthetic-private-home:1"]
                    self.assertEqual(expected, trace)

    def test_router_rejects_other_commands_before_any_helper(self):
        for policy in runtime.POLICIES:
            for args in ([], ["kiqsched", "extra"], ["all"], ["layout"], ["gfx"], ["claim"], ["wreg"]):
                with self.subTest(policy=policy, args=args):
                    result, trace = self.invoke(policy, args)
                    self.assertEqual(64, result.returncode, result.stderr)
                    self.assertEqual([], trace)

    def test_router_observation_or_helper_failure_is_terminal(self):
        for policy, helper in runtime.POLICIES.items():
            result, trace = self.invoke(policy, ["kiqsched"], "sample-before")
            self.assertEqual(75, result.returncode)
            self.assertEqual(["sample-before"], trace)
            result, trace = self.invoke(policy, ["kiqsched"], helper)
            self.assertEqual(75, result.returncode)
            self.assertEqual(2, len(trace))

    def test_router_configuration_is_explicit_and_paths_are_quoted(self):
        for args in (("relative", "/usr/bin/python3", "c.py", "control"),
                     ("/tmp/../packet", "/usr/bin/python3", "c.py", "control"),
                     ("/tmp/packet", "python3", "c.py", "control"),
                     ("/tmp/packet", "/usr/bin/python3", "../c.py", "control"),
                     ("/tmp/packet\ninjection", "/usr/bin/python3", "c.py", "control"),
                     ("/tmp/packet", "/usr/bin/python3", "c.py", "automatic")):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    runtime.render_router(*args)


if __name__ == "__main__":
    unittest.main()
