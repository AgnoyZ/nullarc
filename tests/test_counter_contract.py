"""Exercise the instrumentation contract between the kernel sources, the phase-1 capture and the analysis.

Every case runs the real tools/phx_counter_contract.py. The interesting ones copy the real tree into a
temporary directory and break exactly one thing, so the test says "this rename would have cost a hardware
session" rather than "my regex still matches my own fixture".
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/phx_counter_contract.py"
COPY = ("src", "docs/analysis.md", "tools/phx_baseline.sh", "tools/phxctl/phxboot.sh")


def run(root, *arguments):
    return subprocess.run([sys.executable, str(TOOL), "--root", str(root), *arguments],
                          capture_output=True, text=True, timeout=300)


def report_of(root):
    result = run(root, "--json")
    return result, json.loads(result.stdout)


class ContractTests(unittest.TestCase):
    def broken_tree(self, directory, relative, old, new):
        """A copy of the real tree with exactly one byte-level change, so the failure is the change."""
        tree = Path(directory) / "tree"
        for item in COPY:
            source = ROOT / item
            target = tree / item
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copyfile(source, target)
        path = tree / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text, f"the test's anchor vanished from {relative}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        return tree

    def test_the_real_tree_holds_the_contract(self):
        result = run(ROOT, "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["contract_holds"], report["violations"])
        self.assertEqual(report["violations"], [])
        self.assertFalse(report["claims"]["hardware_execution_established"])
        self.assertEqual(set(report["defaults"]), {
            "debug.phxfb_alias", "debug.phxfb_vbl_staged", "debug.nvaccel_iop_sse", "debug.nvaccel_iop_damage",
            "debug.nvaccel_iop_vsync", "debug.nvaccel_vm_sticky", "debug.phxbos_flush", "debug.nvaccel_iop_flip",
        })
        self.assertEqual(report["defaults"]["debug.phxfb_alias"], 1)
        self.assertEqual(report["defaults"]["debug.nvaccel_iop_sse"], 0)
        self.assertEqual(report["defaults"]["debug.nvaccel_iop_damage"], 0)

    def test_renaming_a_counter_the_capture_reads_is_a_violation(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = self.broken_tree(temporary, "tools/phx_baseline.sh",
                                    "debug.nvaccel_iop_gap2", "debug.nvaccel_iop_gap_two")
            result, report = report_of(tree)
            self.assertEqual(result.returncode, 1, result.stdout)
            checks = {(item["check"], item["name"]) for item in report["violations"]}
            self.assertIn(("capture_reads_undeclared_oid", "debug.nvaccel_iop_gap_two"), checks)
            self.assertIn(("verdict_counter_not_captured", "debug.nvaccel_iop_gap2"), checks)

    def test_dropping_a_verdict_counter_from_the_capture_is_a_violation(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = self.broken_tree(temporary, "tools/phx_baseline.sh",
                                    " debug.nvaccel_iop_vsync_late ", " ")
            result, report = report_of(tree)
            self.assertEqual(result.returncode, 1, result.stdout)
            checks = {(item["check"], item["name"]) for item in report["violations"]}
            self.assertIn(("verdict_counter_not_captured", "debug.nvaccel_iop_vsync_late"), checks)

    def test_changing_a_knob_default_is_a_violation(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = self.broken_tree(temporary, "src/phxaccel/accel/phxfb.cpp",
                                    "static int gAlias = 1;", "static int gAlias = 0;")
            result, report = report_of(tree)
            self.assertEqual(result.returncode, 1, result.stdout)
            changed = [item for item in report["violations"] if item["check"] == "default_changed"]
            self.assertEqual([item["name"] for item in changed], ["debug.phxfb_alias"])
            self.assertIn("phase-1 plan assumes 1", changed[0]["detail"])

    def test_a_documented_name_that_no_longer_exists_is_a_violation(self):
        with tempfile.TemporaryDirectory() as temporary:
            tree = self.broken_tree(temporary, "docs/analysis.md",
                                    "## 5. Hypotheses", "`debug.phxfb_vanished` is read too.\n\n## 5. Hypotheses")
            result, report = report_of(tree)
            self.assertEqual(result.returncode, 1, result.stdout)
            checks = {(item["check"], item["name"]) for item in report["violations"]}
            self.assertIn(("docs_name_undeclared_oid", "debug.phxfb_vanished"), checks)

    def test_an_undocumented_writable_knob_warns_without_failing(self):
        result, report = report_of(ROOT)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertTrue(report["warnings"])
        self.assertTrue(all(item["check"] == "writable_oid_undocumented" for item in report["warnings"]),
                        report["warnings"])
        self.assertEqual(report["violations"], [])

    def test_the_report_is_written_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "contract"
            first = run(ROOT, "--out", str(out))
            self.assertEqual(first.returncode, 0, first.stderr)
            written = json.loads((out / "counter-contract.json").read_text(encoding="utf-8"))
            self.assertTrue(written["contract_holds"])
            second = run(ROOT, "--out", str(out))
            self.assertEqual(second.returncode, 2)
            self.assertIn("exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
