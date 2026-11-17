"""Reject misleading native-diagnostic transcripts; no device framework or GPU."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import test_upstream34_ib_preamble as runner


class PreambleResultTests(unittest.TestCase):
    def result(self, fault='ok', policy='control'):
        code, events = runner.expected(fault)
        stdout = []
        for stage in (1, 2):
            n = events.count(f'wait-{stage}')
            transport = fault in tuple(f'wait-{stage}-{k}' for k in ('status', 'short', 'long'))
            for index in range(n - int(transport)):
                stdout.append(json.dumps({'pass': stage - 1, 'budget_ns': (0, 50000, 2000000000)[index],
                                          'busy': int(index < n - 1), 'elapsed_ns': 4000}))
        if not code:
            stdout.append(runner.CHECK if fault == 'check-ok' else runner.marker(policy))
        stderr = 'HOLD: synthetic failure\n' if 'hold' in events else ''
        summary = runner.expected_mismatch_summary(fault)
        if summary is not None:
            stderr += 'IB-MISMATCH-SUMMARY ' + json.dumps(summary) + '\n'
        stderr += 'fake-native-shader-summary ' + json.dumps({'events': events}) + '\n'
        return subprocess.CompletedProcess([], code, '\n'.join(stdout) + '\n', stderr)

    def test_logged_pending_wait_is_not_transport_failure(self):
        for stage in (1, 2):
            for kind in ('short', 'cap'):
                fault = f'wait-{stage}-pending-{kind}'
                runner.check_result(self.result(fault), fault, 'control')

    def test_wait_transport_failure_does_not_log_response(self):
        for stage in (1, 2):
            for kind in ('status', 'short', 'long'):
                fault = f'wait-{stage}-{kind}'
                runner.check_result(self.result(fault), fault, 'control')

    def test_no_device_access_for_legacy_cli(self):
        for fault in ('legacy-run', 'legacy-fresh', 'legacy-reuse', 'legacy-publish'):
            self.assertEqual(runner.expected(fault), (64, []))

    def test_reject_false_success_and_missing_wait(self):
        result = self.result()
        result.stdout = runner.marker('control') + '\n'
        with self.assertRaises(RuntimeError):
            runner.check_result(result, 'ok', 'control')
        result = self.result('wait-2-timeout')
        result.stdout += runner.marker('control') + '\n'
        with self.assertRaises(RuntimeError):
            runner.check_result(result, 'wait-2-timeout', 'control')

    def test_reject_cleanup_after_failed_exercise(self):
        result = self.result('submit-2-status')
        result.stderr = result.stderr.replace('"hold"', '"cpu-unmap", "close", "hold"')
        with self.assertRaises(RuntimeError):
            runner.check_result(result, 'submit-2-status', 'control')

    def test_stale_output_rejected_for_every_policy(self):
        for policy in runner.POLICIES:
            self.assertIn('hold', runner.expected('stale-output-2')[1])
            result = self.result('stale-output-2', policy)
            result.stderr = ('FAIL: mismatch at byte 8208 (pass=1 actual=0xde expected=0xdf)\n' + result.stderr)
            runner.check_result(result, 'stale-output-2', policy)

    def test_mismatch_summary_is_required_and_checked(self):
        for fault in ('stale-output-2', 'poison-output-2', 'mixed-output-2', 'byte-2-16383'):
            result = self.result(fault)
            if fault == 'stale-output-2':
                result.stderr = 'FAIL: mismatch at byte 8208 (pass=1 actual=0xde expected=0xdf)\n' + result.stderr
            runner.check_result(result, fault, 'control')
            for changed in (result.stderr.replace('IB-MISMATCH-SUMMARY ', 'REMOVED '),
                            result.stderr.replace('"mismatch_bytes": ', '"mismatch_bytes": 999'),
                            result.stderr.replace('"original_mismatch_reobserved": true', '"original_mismatch_reobserved": false')):
                with self.assertRaises((RuntimeError, json.JSONDecodeError)):
                    runner.check_result(subprocess.CompletedProcess([],result.returncode,result.stdout,changed),fault,'control')

    def test_policy_markers_cannot_be_interchanged(self):
        for actual in runner.POLICIES:
            for requested in runner.POLICIES:
                if actual == requested:
                    runner.check_result(self.result(policy=actual), 'ok', requested)
                else:
                    with self.assertRaises(RuntimeError):
                        runner.check_result(self.result(policy=actual), 'ok', requested)
        with self.assertRaises(ValueError):
            runner.marker('unknown')

    def test_batch_requires_complete_matching_frames(self):
        frame = 'fake-native-case-end {"index":0,"returncode":75}\n'
        result = subprocess.CompletedProcess([], 0, 'output\n' + frame, 'error\n' + frame)
        parsed = runner.batch_results(result, 1)
        self.assertEqual((parsed[0].returncode, parsed[0].stdout, parsed[0].stderr), (75, 'output\n', 'error\n'))
        for changed in (
                subprocess.CompletedProcess([], 1, result.stdout, result.stderr),
                subprocess.CompletedProcess([], 0, result.stdout, result.stderr + 'trailing'),
                subprocess.CompletedProcess([], 0, result.stdout, result.stderr.replace(':75', ':0')),
                subprocess.CompletedProcess([], 0, result.stdout.replace(':0,', ':1,'), result.stderr),
                subprocess.CompletedProcess([], 0, result.stdout.replace(':0,', ':false,'), result.stderr),
                subprocess.CompletedProcess([], 0, result.stdout, ''),
        ):
            with self.assertRaises(RuntimeError):
                runner.batch_results(changed, 1)
        with self.assertRaises(RuntimeError):
            runner.batch_results(result, 2)


if __name__ == '__main__':
    unittest.main()
