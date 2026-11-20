#!/usr/bin/env python3
"""CPU-only trace fixtures: reject missing/early/failed timing evidence."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('R2_profile', Path(__file__).resolve().parents[1] /
                                             'tools/build34_present_profile.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class EvidenceTests(unittest.TestCase):
    GOOD = ('READY 100\nENTRY 7 110 0\nWAIT_RETURN 354\nPREPARE_RETURN 1029\n'
            'TX 7 110 510 150 20 1 0 0 1964 0\nEND 600\n\n')

    def test_real_return_fixture_and_trailing_blank(self):
        r = m.parse(self.GOOD)
        self.assertEqual(r['completed_transactions'], 1)
        self.assertEqual(r['transaction']['sum_ns'], 400)
        self.assertEqual(r['residual_including_copy_and_other_work']['sum_ns'], 230)

    def test_idle_window_is_not_evidence(self):
        with self.assertRaisesRegex(ValueError, 'no complete'):
            m.parse('READY 100\nEND 600\n\n')

    def test_unknown_endpoint_failure_or_missing_entry_refused(self):
        for source in (self.GOOD.replace('1964 0', '1965 0'), self.GOOD.replace('354', '355'),
                       self.GOOD.replace('1029', '1030'), self.GOOD.replace('1964 0', '1964 1'),
                       self.GOOD.replace('ENTRY 7 110 0\n', ''), self.GOOD.replace('END 600\n', ''),
                       self.GOOD.replace('150 20', '450 20'), self.GOOD + 'ERROR\n',
                       self.GOOD.replace('1 0 0 1964', '1 1 0 1964')):
            with self.subTest(source=source), self.assertRaises(ValueError):
                m.parse(source)

    def test_per_CPU_flush_order_and_incomplete_boundary_are_explicit(self):
        source = self.GOOD.replace('END 600', 'ENTRY 7 550 0\nEND 600')
        self.assertEqual(m.parse(source)['incomplete_at_trace_end'], 1)
        lines = source.splitlines()
        self.assertEqual(m.parse('\n'.join(reversed(lines))), m.parse(source))

    def test_overlaps_duplicates_diagnostics_and_nonzero_exit_refused(self):
        for extra in ('TX 7 110 510 150 20 1 0 0 1964 0\n', 'ENTRY 7 110 0\n',
                      'ENTRY 7 120 0\nTX 7 120 520 0 0 0 0 0 1964 0\n',
                      'REENTER\n', 'UNFINISHED_STAGE\n', 'TX -1\n'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                m.parse(self.GOOD + extra)
        with self.assertRaises(ValueError): m.parse(self.GOOD, code=1)
        with self.assertRaises(ValueError): m.parse(self.GOOD, stderr='drop')

    def test_program_is_module_and_transaction_scoped_and_finite(self):
        s = m.trace_program()
        self.assertEqual(s.count('fbt:com.luuumi.PhxAccel:'), 8)
        self.assertNotIn('pid == ', s)
        self.assertIn('profile:::tick-8sec', s)
        self.assertNotIn('system(', s)
        self.assertIn('self->txn && self->ws', s)


if __name__ == '__main__':
    unittest.main()
