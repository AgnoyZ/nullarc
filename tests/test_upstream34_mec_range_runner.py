"""Pinned-source and host-result checks; real CLI tests are a separate macOS target."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from upstream34_layout import mec_range
from test_upstream34_mec_range import cases, check_result, expected_result, SUMMARY


class MecRangeTests(unittest.TestCase):
    def base_source(self):
        present = subprocess.run(["git", "cat-file", "-e", mec_range.BASE + "^{commit}"], cwd=ROOT,
                                 capture_output=True, timeout=10)
        if present.returncode:
            self.skipTest("Fixed build34 object unavailable in shallow history; the macOS target requires it")
        return mec_range.read_base("tools/phxctl/mesboot.c")

    def test_exact_pinned_source_round_trip(self):
        original = self.base_source()
        trial = mec_range.transform(original)
        self.assertEqual(original, trial.replace(mec_range.SCHED_TRIAL, mec_range.SCHED)
                         .replace(mec_range.ENTRY_TRIAL, mec_range.ENTRY))
        self.assertEqual(1, trial.count(b"   phx34_mec_range_init();"))
        self.assertIn(b"phx34_mec_range_init();\n   sched_init();", trial)

    def test_drift_rejected_before_materialization(self):
        original = self.base_source()
        for changed in (original + b"\n", original.replace(b"   sched_init();", b"   sched_init(); /* drift */")):
            with self.assertRaises(ValueError):
                mec_range.transform(changed)

    def test_materialization_pins_inputs_and_never_overwrites(self):
        self.base_source()
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "new"
            source, record = mec_range.materialize(destination)
            for name, digest in mec_range.INPUTS.items():
                if name != "mesboot.c":
                    self.assertEqual(digest, mec_range.sha((source / name).read_bytes()))
            self.assertFalse(record["installed"])
            self.assertFalse(record["GPU_executed"])
            self.assertTrue(record["build34_only"])
            self.assertFalse(record["kernel_or_production_helpers_modified"])
            self.assertEqual(mec_range.sha(mec_range.read_base("src/phxbringup/PhxBringup.cpp")),
                             record["current_production_inputs_sha256"]["src/phxbringup/PhxBringup.cpp"])
            self.assertEqual({"control": 0, "mec-range": 1}, record["policies"])
            with self.assertRaises(ValueError):
                mec_range.materialize(destination)

    def test_current_source_drift_is_refused_before_creating_output(self):
        self.base_source()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = ("src/phxbringup/PhxBringup.cpp", "src/phxbringup/PhxNativeABI.h",
                     "tools/phxctl/mesboot.c", "tools/phxctl/PhxUpstream34Layout.h",
                     "LICENSE", "LICENSES/MIT.txt", "THIRD_PARTY_NOTICES.md")
            expected = {name: b"pinned original source\n" for name in paths}
            for name, data in expected.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            verified = mec_range.verify_current_inputs(expected, root)
            self.assertEqual(set(paths), set(verified))
            for name in paths:
                with self.subTest(path=name):
                    path = root / name
                    for content in (b"different source\n", None):
                        if content is None:
                            path.unlink()
                        else:
                            path.write_bytes(content)
                        with mock.patch.object(mec_range, "ROOT", root), \
                                mock.patch.object(mec_range, "protected_base_inputs", return_value=expected):
                            with self.assertRaisesRegex(ValueError, "Current source differs from original build34"):
                                mec_range.materialize(root / "output")
                        self.assertFalse((root / "output").exists())
                    path.write_bytes(expected[name])

    def test_case_accounting_and_no_scheduler_after_refusal(self):
        for policy in (0, 1):
            names = list(cases(policy))
            self.assertEqual(len(names), len(set(names)))
            for fault in names:
                status, counts = expected_result(policy, fault)
                self.assertEqual(fault == "ok", status == 0)
                self.assertEqual(int(status == 0), counts["scheduler_entered"])
                self.assertEqual(0, counts["closes"])
                stderr = ""
                if fault.startswith(("write-bad-", "write-ones-", "read-bad-", "read-ones-")):
                    step = fault.rsplit("-", 1)[1]
                    phase = "write-readback" if fault.startswith("write-") else "readback"
                    stderr = f"mec-range trial: step={step} {phase}=0x00000000; stopping"
                result = subprocess.CompletedProcess([], status, SUMMARY + json.dumps(counts), stderr)
                self.assertEqual(counts, check_result(result, policy, fault))

    def test_first_write_and_read_failures_prevent_second_write(self):
        for fault in ("write-status-1", "write-bad-1", "write-ones-1", "read-status-1", "read-bad-1", "read-ones-1"):
            status, counts = expected_result(1, fault)
            self.assertNotEqual(0, status)
            self.assertEqual(1, counts["range_writes"])
            self.assertEqual(0, counts["scheduler_entered"])

    def test_validator_rejects_false_success_continuation_and_missing_diagnostic(self):
        status, counts = expected_result(1, "read-bad-2")
        for result in (subprocess.CompletedProcess([], 0, SUMMARY + json.dumps(counts), ""),
                       subprocess.CompletedProcess([], status, SUMMARY + json.dumps({**counts, "scheduler_entered": 1}), ""),
                       subprocess.CompletedProcess([], status, SUMMARY + json.dumps({**counts, "closes": False}), ""),
                       subprocess.CompletedProcess([], status, SUMMARY + json.dumps(counts), "")):
            with self.assertRaises(RuntimeError):
                check_result(result, 1, "read-bad-2")

    def test_unknown_policies_and_cases_are_refused(self):
        for policy, name in ((2, "ok"), (True, "ok"), (0, "read-bad-1"), (1, "typo")):
            with self.assertRaises(ValueError):
                expected_result(policy, name)


if __name__ == "__main__":
    unittest.main()
