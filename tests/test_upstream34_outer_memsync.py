"""CPU-only transformation/refusal checks; no device or kernel compilation."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.upstream34_layout import outer_memsync as m


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = m.mec_range.read_base('src/phxbringup/PhxBringup.cpp')
        cls.function = m.ring_padding.extract(cls.original.decode())

    def test_original_identity(self):
        self.assertEqual(m.candidate_source(self.original, 'original'), self.original)
        self.assertEqual(m.transform(self.function, 'original'), self.function)

    def test_original_and_transformed_drift_rejected(self):
        for policy in m.POLICIES:
            with self.assertRaises(ValueError):
                m.candidate_source(self.original + b'\n', policy)
            with self.assertRaises(ValueError):
                m.transform(self.function + '\n', policy)
        for policy in m.POLICIES[1:]:
            with self.assertRaises(ValueError):
                m.transform(m.transform(self.function, policy), policy)

    def test_unknown_policy_refused(self):
        with self.assertRaises(ValueError):
            m.transform(self.function, 'padding')

    def test_equal_footprint_prefixes_and_exact_payloads(self):
        expected = {
            'nop-prefix': [0xc0061000, 0, 0, 0, 0, 0, 0, 0],
            'acquire-prefix': [0xc0065800, 0, 0xffffffff, 0xffffff, 0, 0, 10,
                               (1 << 0) | (1 << 4) | (1 << 5) | (1 << 7) |
                               (1 << 8) | (1 << 9) | (1 << 14) | (1 << 15)]}
        for policy, words in expected.items():
            changed = m.transform(self.function, policy)
            prefix = changed.split(m.OLD_START)[1].split('    for (uint32_t i = 0;')[0]
            self.assertTrue(prefix.startswith('    if (!q.gfx) {\n'))
            self.assertEqual(prefix.count('ringPut(q, k++,'), 8)
            for word in words:
                self.assertIn('0x%08xu' % word, prefix)
            self.assertIn(m.NEW_NEED, changed)
            self.assertNotIn('0xffff1000u', changed)

    def test_only_reservation_and_prefix_change(self):
        for policy in m.POLICIES[1:]:
            changed = m.candidate_source(self.original, policy).decode()
            function = m.transform(self.function, policy)
            self.assertEqual(changed.replace(function, self.function).encode(), self.original)
            self.assertEqual(function.split('    const uint64_t seq = ++gSeq;')[1],
                             self.function.split('    const uint64_t seq = ++gSeq;')[1])
            self.assertEqual(function.split('    for (uint32_t i = 0;')[1],
                             self.function.split('    for (uint32_t i = 0;')[1])

    def test_ambiguous_sites_refused_even_with_injected_hash(self):
        for fragment in (m.OLD_NEED, m.OLD_START):
            bad = self.function + fragment
            with patch.object(m.ring_padding, 'FUNCTION_SHA', hashlib.sha256(bad.encode()).hexdigest()):
                with self.assertRaises(ValueError):
                    m.transform(bad, 'acquire-prefix')

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=m.ROOT / 'build') as dest:
            with self.assertRaises(ValueError):
                m.exercise(Path(dest))

    def test_output_outside_worktree_build_refused(self):
        with tempfile.TemporaryDirectory() as dest:
            with self.assertRaises(ValueError):
                m.exercise(Path(dest) / 'new-output')

    def test_non_x86_refused_before_output(self):
        with patch.object(m.platform, 'machine', return_value='arm64'):
            with self.assertRaises(RuntimeError):
                m.exercise(m.ROOT / 'build/never-created-outer-memsync-private')


if __name__ == '__main__':
    unittest.main()
