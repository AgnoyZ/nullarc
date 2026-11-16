import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_native_ib_freshness import CASES, check_result, expected, exercise, marker
from test_native_shader_probe import CHECK


class NativeIbFreshnessRunnerTests(unittest.TestCase):
    def result(self, fault='ok', policy='fresh'):
        code, events = expected(fault, policy)
        rows = []
        for stage in (1, 2):
            count = events.count(f'wait-{stage}')
            if fault.startswith(f'wait-{stage}-') and fault.endswith(('-status', '-short', '-long')) and '-pending-' not in fault:
                count -= 1
            for index in range(max(count, 0)):
                rows.append({'pass': stage - 1, 'budget_ns': [0, 50000, 2000000000][index],
                    'busy': int(index < count - 1 or fault == f'wait-{stage}-timeout'), 'elapsed_ns': 4000})
        stdout = '\n'.join(json.dumps(row) for row in rows)
        if not code:
            stdout = CHECK if fault == 'check-ok' else stdout + '\n' + marker(policy)
        errors = 'HOLD: retained\n' if 'hold' in events else ''
        if fault.startswith('slot-'):
            errors += f'mismatch at byte {0x1200 + int(fault[5:]) * 4} (pass=1 actual=0x00 expected=0x01)\n'
        if fault == 'stale-output-2' or (fault == 'stale-ib-fetch-2' and policy == 'reuse'):
            errors += 'mismatch at byte 8208 (pass=1 actual=0xde expected=0xdf)\n'
        errors += 'fake-native-shader-summary ' + json.dumps({'events': events})
        return subprocess.CompletedProcess([], code, stdout, errors)

    def test_case_set_and_both_inactive_IB_and_guard_coverage(self):
        self.assertEqual(len(CASES), len(set(CASES)))
        self.assertEqual(80, sum(case.startswith('slot-') for case in CASES))
        for fault in ('code-1-0', 'ib-2-79', 'output-2-255', 'byte-2-16383', 'legacy-run'):
            self.assertIn(fault, CASES)
        for policy in ('reuse', 'fresh'):
            for fault in CASES:
                check_result(self.result(fault, policy), fault, policy)

    def test_stale_models_have_distinct_and_explicit_limits(self):
        self.assertEqual(75, expected('stale-output-2', 'fresh')[0])
        self.assertEqual(75, expected('stale-output-2', 'reuse')[0])
        self.assertEqual(75, expected('stale-ib-fetch-2', 'reuse')[0])
        self.assertEqual(0, expected('stale-ib-fetch-2', 'fresh')[0])

    def test_HOLD_never_unmaps_closes_or_submits_after_failure(self):
        for fault in CASES:
            _, events = expected(fault, 'fresh')
            if 'hold' in events:
                self.assertEqual('hold', events[-1])
                for forbidden in ('cpu-unmap', 'gpu-unmap', 'free', 'ctx-free', 'close'):
                    self.assertNotIn(forbidden, events)
                self.assertLessEqual(sum(event.startswith('submit-') for event in events), 2)

    def test_false_success_bad_trace_and_missing_HOLD_refused(self):
        result = self.result('stale-output-2')
        for bad in (
            subprocess.CompletedProcess([], 0, result.stdout, result.stderr),
            subprocess.CompletedProcess([], 75, marker('fresh'), result.stderr),
            subprocess.CompletedProcess([], 75, result.stdout, result.stderr.replace('HOLD:', 'missing:')),
            subprocess.CompletedProcess([], 75, result.stdout, result.stderr.replace('"hold"', '"close"')),
        ):
            with self.assertRaises(RuntimeError):
                check_result(bad, 'stale-output-2', 'fresh')

    def test_pending_waits_and_check_only_scope(self):
        for stage in (1, 2):
            for kind, calls in (('short', 2), ('cap', 3)):
                fault = f'wait-{stage}-pending-{kind}'
                _, events = expected(fault, 'fresh')
                self.assertEqual(calls, events.count(f'wait-{stage}'))
                self.assertEqual(2, sum(event.startswith('submit-') for event in events))
        _, events = expected('check-ok', 'reuse')
        self.assertNotIn('ctx-alloc', events)
        self.assertEqual(64, expected('legacy-run', 'fresh')[0])

    def test_source_keeps_two_dispatches_modes_and_original_HOLD(self):
        source = (ROOT / 'tools/native_ib_freshness_probe.cpp').read_text()
        self.assertEqual(2, source.count('pass < 2'))
        self.assertIn('const size_t selected = ibOffset[fresh ? pass : 0]', source)
        self.assertIn('if (pass && !fresh)', source)
        self.assertIn('for (;;) pause();', source)
        self.assertIn('i < bytes', source)
        self.assertIn('usleep(250000)', source)
        for forbidden in ('system(', 'popen(', 'kextload', 'shutdown', 'PHXN_SEL_DBG_'):
            self.assertNotIn(forbidden, source)

    def test_unknown_policy_case_windows_and_existing_output_refused(self):
        with self.assertRaises(ValueError): expected('ok', 'unknown')
        with self.assertRaises(ValueError): expected('unknown', 'fresh')
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch('test_native_ib_freshness.platform.system', return_value='Windows'):
                with self.assertRaises(RuntimeError): exercise(Path(directory) / 'new')
            with self.assertRaises(RuntimeError): exercise(directory)


if __name__ == '__main__':
    unittest.main()
