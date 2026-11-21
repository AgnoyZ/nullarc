#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline source and prospective-manifest checks; no root/driver/GPU calls."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build34_map_candidate as candidate


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {n: (ROOT / n).read_bytes() for n in candidate.common.SOURCE_INPUTS}
        self.proposed = dict(self.baseline)
        self.proposed[candidate.DRIVER] = candidate.observation.stage_baseline(self.baseline[candidate.DRIVER].decode()).encode()

    def test_exact_single_observation_insertion(self):
        before, after = copy.deepcopy(self.baseline), copy.deepcopy(self.proposed)
        candidate.verify_sources(self.baseline, self.proposed)
        self.assertEqual(self.baseline, before)
        self.assertEqual(self.proposed, after)

    def test_unknown_driver_or_protected_input_refuses(self):
        for name in self.proposed:
            changed = dict(self.proposed)
            changed[name] += b'\n'
            with self.subTest(name=name), self.assertRaises(ValueError):
                candidate.verify_sources(self.baseline, changed)
        with self.assertRaises(ValueError):
            candidate.verify_sources({**self.baseline, 'extra': b'x'}, self.proposed)

    def test_full_R3_stage_is_not_observer_candidate(self):
        changed = dict(self.proposed)
        changed[candidate.DRIVER] = candidate.observation.stage_factory(self.baseline[candidate.DRIVER].decode()).encode()
        with self.assertRaises(ValueError):
            candidate.verify_sources(self.baseline, changed)

    def test_transform_is_pinned_to_tested_observation(self):
        path = ROOT / 'tools/build34_map_observation.py'
        self.assertEqual(candidate.common.sha(path.read_bytes()), candidate.TRANSFORM_SHA)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {candidate.EXE: {'sha256': candidate.BASE_BINARY, 'bytes': 10},
                         'Contents/Info.plist': {'sha256': 'unchanged-plist', 'bytes': 5},
                         'Contents/_CodeSignature/CodeResources': {'sha256': 'unchanged-signature', 'bytes': 8}}
        self.observer = copy.deepcopy(self.baseline)
        self.observer[candidate.EXE] = {'sha256': 'observer', 'bytes': 20}
        self.efi = {candidate.ACTIVE + n: copy.deepcopy(v) for n, v in self.baseline.items()}
        self.efi.update({'unrelated/' + str(i): {'sha256': str(i), 'bytes': i} for i in range(354)})
        self.efi['Microsoft/Boot/bootmgfw.efi'] = {'sha256': 'retained-external', 'bytes': 400}
        self.assertEqual(len(self.efi), 358)

    def test_only_executable_changes_and_inputs_are_not_mutated(self):
        original = copy.deepcopy(self.efi)
        after = candidate.derive_efi_manifest(self.efi, self.baseline, self.observer)
        self.assertEqual(self.efi, original)
        self.assertEqual(set(after), set(original))
        self.assertEqual({n for n in original if after[n] != original[n]}, {candidate.ACTIVE + candidate.EXE})
        self.assertEqual(after['Microsoft/Boot/bootmgfw.efi'], original['Microsoft/Boot/bootmgfw.efi'])
        after[candidate.ACTIVE + candidate.EXE]['bytes'] = 0
        self.assertEqual(self.observer[candidate.EXE]['bytes'], 20)

    def test_incomplete_or_unknown_active_EFI_refuses(self):
        changed = copy.deepcopy(self.efi)
        changed.pop('unrelated/0')
        with self.assertRaises(ValueError):
            candidate.derive_efi_manifest(changed, self.baseline, self.observer)
        changed = copy.deepcopy(self.efi)
        changed[candidate.ACTIVE + candidate.EXE]['sha256'] = 'unknown'
        with self.assertRaises(ValueError):
            candidate.derive_efi_manifest(changed, self.baseline, self.observer)

    def test_no_change_extra_bundle_file_or_metadata_change_refuses(self):
        choices = [copy.deepcopy(self.baseline), copy.deepcopy(self.observer), copy.deepcopy(self.observer)]
        choices[1]['extra'] = {'sha256': 'extra', 'bytes': 1}
        choices[2]['Contents/Info.plist']['sha256'] = 'unknown'
        for value in choices:
            with self.subTest(keys=list(value)), self.assertRaises(ValueError):
                candidate.derive_efi_manifest(self.efi, self.baseline, value)


if __name__ == '__main__':
    unittest.main()
