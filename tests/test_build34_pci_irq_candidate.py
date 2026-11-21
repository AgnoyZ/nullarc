#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build34_pci_irq_candidate as candidate


class ArtifactGates(unittest.TestCase):
    def setUp(self):
        self.source = {n: (ROOT / n).read_bytes() for n in candidate.common.SOURCE_INPUTS}
        self.evidence = json.loads((ROOT / candidate.EVIDENCE).read_bytes())
        self.exe = candidate.mapped.EXE
        self.restore = {self.exe: candidate.CONTROL_BINARY, 'Contents/Info.plist': 'plist',
                        'Contents/_CodeSignature/CodeResources': 'signature'}
        self.observer = {**self.restore, self.exe: 'new-executable'}

    def test_source_inputs_and_startup_delta(self):
        pair = candidate.sources(self.source, self.evidence)
        self.assertEqual(set(pair), {'restore', 'pci-observer'})
        protected = set(self.source) - {candidate.common.DRIVER}
        for role in pair.values():
            self.assertTrue(all(role[n] == self.source[n] for n in protected))

    def test_drifted_offline_evidence_is_refused(self):
        for key in ('status', 'kernel_build', 'native_import_count', 'new_native_imports', 'sdk_commit',
                    'control_source_sha256', 'observer_source_sha256'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                candidate.sources(self.source, {**self.evidence, key: None})

    def test_requires_exact_restore_and_only_one_kernel_executable_delta(self):
        candidate.bundle_pair(self.restore, self.restore.copy(), self.observer)
        for altered in (self.restore, {**self.observer, 'Contents/Info.plist': 'changed'},
                        {**self.observer, 'extra': 'added'}, {self.exe: 'new-executable'}):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                candidate.bundle_pair(self.restore, self.restore, altered)
        wrong_restore = {**self.restore, self.exe: 'wrong-restore'}
        with self.assertRaises(ValueError):
            candidate.bundle_pair(wrong_restore, wrong_restore, self.observer)


if __name__ == '__main__':
    unittest.main()
