#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Refusal checks for the separate wait-candidate source gate; no build/device."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("wait_build", ROOT / "tools/build34_wait_deadline.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class SourceGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = {name: subprocess.check_output(["git", "show", m.BASE + ":" + name], cwd=ROOT)
                        for name in m.INPUTS}
        cls.current = {name: (ROOT / name).read_bytes() for name in m.INPUTS}

    def test_exact_candidate(self):
        self.assertEqual(m.verify_blobs(self.baseline, self.current)[m.DRIVER], m.CANDIDATE_SHA)

    def test_only_wait_method_differs(self):
        before, after = m.method(self.baseline[m.DRIVER]), m.method(self.current[m.DRIVER])
        self.assertEqual(self.baseline[m.DRIVER].replace(before, after), self.current[m.DRIVER])

    def test_baseline_not_admitted_as_candidate(self):
        with self.assertRaises(ValueError):
            m.verify_blobs(self.baseline, self.baseline)

    def test_unknown_wait_body_refused(self):
        changed = dict(self.current)
        changed[m.DRIVER] += b"\n"
        with self.assertRaises(ValueError):
            m.verify_blobs(self.baseline, changed)

    def test_submission_drift_refused(self):
        changed = dict(self.current)
        changed[m.DRIVER] = changed[m.DRIVER].replace(b"0x0000c3b1u", b"0x00000000u")
        self.assertNotEqual(changed[m.DRIVER], self.current[m.DRIVER])
        with self.assertRaises(ValueError):
            m.verify_blobs(self.baseline, changed)

    def test_other_build_refused(self):
        for build in (b"41", b"42"):
            changed = dict(self.current)
            changed[m.DRIVER] = changed[m.DRIVER].replace(b"PHX_KEXT_BUILD 34u", b"PHX_KEXT_BUILD " + build + b"u")
            with self.subTest(build=build), self.assertRaises(ValueError):
                m.verify_blobs(self.baseline, changed)

    def test_every_other_input_drift_refused(self):
        for name in m.INPUTS:
            if name == m.DRIVER:
                continue
            changed = dict(self.current)
            changed[name] += b"\n"
            with self.subTest(name=name), self.assertRaises(ValueError):
                m.verify_blobs(self.baseline, changed)

    def test_missing_and_extra_inputs_refused(self):
        for name in m.INPUTS:
            changed = dict(self.current)
            del changed[name]
            with self.subTest(name=name), self.assertRaises(ValueError):
                m.verify_blobs(self.baseline, changed)
        changed = dict(self.current, extra=b"unexpected")
        with self.assertRaises(ValueError):
            m.verify_blobs(self.baseline, changed)

    def test_baseline_drift_refused(self):
        changed = dict(self.baseline)
        changed[m.DRIVER] += b"\n"
        with self.assertRaises(ValueError):
            m.verify_blobs(changed, self.current)

    def test_historical_admission_unchanged_and_refuses_candidate(self):
        from upstream34_layout import submit_memsync
        self.assertEqual(submit_memsync.SOURCE_SHA, m.BASE_SHA)
        self.assertEqual(submit_memsync.extract(self.baseline[m.DRIVER]),
                         submit_memsync.extract(submit_memsync.reviewed_inputs()[m.DRIVER]))
        with self.assertRaises(ValueError):
            submit_memsync.extract(self.current[m.DRIVER])


if __name__ == "__main__":
    unittest.main()
