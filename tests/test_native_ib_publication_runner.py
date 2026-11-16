import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_native_ib_publication import CASES, check_result, expected, exercise, marker
from test_native_shader_probe import CHECK


class NativeIbPublicationRunnerTests(unittest.TestCase):
    def result(self, fault='ok', policy='ib-publish'):
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
        if fault in ('stale-output-2', 'stale-ib-fetch-2') or (fault == 'stale-ib-cpu-2' and policy == 'control'):
            errors += 'mismatch at byte 8208 (pass=1 actual=0xde expected=0xdf)\n'
        errors += 'fake-native-shader-summary ' + json.dumps({'events': events})
        return subprocess.CompletedProcess([], code, stdout, errors)

    def test_complete_distinct_case_set_and_accounting(self):
        self.assertEqual(len(CASES), len(set(CASES)))
        for policy in ('control', 'ib-publish'):
            for fault in CASES:
                check_result(self.result(fault, policy), fault, policy)

    def test_only_second_rewritten_IB_is_published(self):
        _, events = expected('ok', 'ib-publish')
        lines = [f'ib-clflush-{n}' for n in range(5)] + ['ib-publication-fence']
        index = events.index('submit-2')
        self.assertEqual(lines, events[index - 6:index])
        self.assertLess(events.index('wait-1'), index - 6)
        self.assertFalse(any(v.startswith('ib-') for v in expected('ok', 'control')[1]))
        for policy in ('control', 'ib-publish'):
            self.assertFalse(any(v.startswith('ib-') for v in expected('check-ok', policy)[1]))
            self.assertFalse(any(v.startswith('ib-') for v in expected('output-1-0', policy)[1]))

    def test_CPU_capability_failures_precede_device_access(self):
        for policy in ('control', 'ib-publish'):
            for fault in ('cpu-no-clflush', 'cpu-line-zero', 'cpu-line-32', 'cpu-line-128'):
                self.assertEqual((4, ['host', 'cpu-clflush-capability']), expected(fault, policy))
            for fault in ('legacy-run', 'legacy-reuse', 'legacy-fresh'):
                self.assertEqual((64, []), expected(fault, policy))

    def test_injected_models_remain_separate_from_hardware_evidence(self):
        self.assertEqual(75, expected('stale-ib-cpu-2', 'control')[0])
        self.assertEqual(0, expected('stale-ib-cpu-2', 'ib-publish')[0])
        for policy in ('control', 'ib-publish'):
            for fault in ('stale-output-2', 'stale-ib-fetch-2'):
                self.assertEqual(75, expected(fault, policy)[0])

    def test_operation_reordering_missing_HOLD_and_false_PASS_refused(self):
        result = self.result()
        for errors in (result.stderr.replace('ib-clflush-0', 'ib-clflush-1'),
                       result.stderr.replace('ib-publication-fence', 'ib-extra-line'),
                       result.stderr.replace('"submit-2"', '"submit-3"')):
            with self.assertRaises(RuntimeError):
                check_result(subprocess.CompletedProcess([], 0, result.stdout, errors), 'ok', 'ib-publish')
        result = self.result('stale-output-2')
        for bad in (subprocess.CompletedProcess([], 0, result.stdout, result.stderr),
                    subprocess.CompletedProcess([], 75, marker('ib-publish'), result.stderr),
                    subprocess.CompletedProcess([], 75, result.stdout, result.stderr.replace('HOLD:', 'missing:'))):
            with self.assertRaises(RuntimeError):
                check_result(bad, 'stale-output-2', 'ib-publish')

    def test_HOLD_stops_cleanup_and_caps_submissions(self):
        for policy in ('control', 'ib-publish'):
            for fault in CASES:
                _, events = expected(fault, policy)
                self.assertLessEqual(sum(e.startswith('submit-') for e in events), 2)
                if 'hold' in events:
                    self.assertEqual('hold', events[-1])
                    self.assertFalse(set(events) & {'cpu-unmap', 'gpu-unmap', 'free', 'ctx-free', 'close'})

    def test_unknown_modes_and_output_overwrite_refused(self):
        with self.assertRaises(ValueError): expected('ok', 'fresh')
        with self.assertRaises(ValueError): expected('unknown', 'control')
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch('test_native_ib_publication.platform.system', return_value='Windows'):
                with self.assertRaises(RuntimeError): exercise(Path(directory) / 'new')
            with self.assertRaises(RuntimeError): exercise(directory)


if __name__ == '__main__':
    unittest.main()
