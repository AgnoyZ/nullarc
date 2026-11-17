# SPDX-License-Identifier: MIT
"""Integrated source identity/refusal tests; never open a GPU client."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.upstream34_layout import submit_memsync as m


class Tests(unittest.TestCase):
    def test_production_matches_exact_hardware_tested_source(self):
        current = (m.ROOT / m.DRIVER).read_bytes()
        self.assertEqual(m.sha(current), m.SOURCE_SHA)
        self.assertEqual(current, m.reviewed_inputs()[m.DRIVER])
        self.assertEqual(m.sha(m.extract(current).encode()), m.FUNCTION_SHA)

    def test_only_two_original_function_sites_change(self):
        original = m.mec_range.read_base(m.DRIVER)
        before = m.outer_memsync.ring_padding.extract(original.decode())
        after = m.extract((m.ROOT / m.DRIVER).read_bytes())
        self.assertEqual(after, m.outer_memsync.transform(before, 'acquire-prefix'))
        self.assertEqual((m.ROOT / m.DRIVER).read_text().replace(after, before).encode(), original)

    def test_original34_admission_still_refuses_modified_source(self):
        with self.assertRaisesRegex(ValueError, 'Current source differs from original build34'):
            m.mec_range.verify_current_inputs(m.mec_range.protected_base_inputs(), m.ROOT)
        with self.assertRaises(ValueError):
            m.outer_memsync.candidate_source((m.ROOT / m.DRIVER).read_bytes(), 'acquire-prefix')

    def test_source_or_function_drift_refused(self):
        current = (m.ROOT / m.DRIVER).read_bytes()
        for data in (current + b'\n', current.replace(b'0x0000c3b1u', b'0x00000000u'),
                     m.mec_range.read_base(m.DRIVER)):
            with self.assertRaises(ValueError):
                m.extract(data)

    def test_other_input_missing_drift_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = {'driver': b'accepted', 'helper': b'preserved'}
            for name, value in expected.items():
                (root / name).write_bytes(value)
            self.assertEqual(set(m.verify_inputs(expected, root)), set(expected))
            for name in expected:
                path = root / name
                path.write_bytes(b'drift')
                with self.assertRaises(ValueError):
                    m.verify_inputs(expected, root)
                path.unlink()
                with self.assertRaises(ValueError):
                    m.verify_inputs(expected, root)
                backing = root / (name + '-backing')
                backing.write_bytes(expected[name]);path.symlink_to(backing)
                with self.assertRaises(ValueError):
                    m.verify_inputs(expected, root)
                path.unlink();path.write_bytes(expected[name])

    def test_destination_and_platform_refused_before_output(self):
        with patch.object(m.platform, 'machine', return_value='arm64'):
            with self.assertRaises(RuntimeError):
                m.exercise(m.ROOT / 'build/never-created-integrated-submit-private')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / 'build/existing'
            existing.mkdir(parents=True)
            with patch.object(m, 'ROOT', root), \
                    patch.object(m.platform, 'machine', return_value='x86_64'), \
                    patch.object(m.shutil, 'which', return_value='clang++'):
                for destination in (existing, root / 'outside'):
                    with self.assertRaises(ValueError):
                        m.exercise(destination)


if __name__ == '__main__':
    unittest.main()
