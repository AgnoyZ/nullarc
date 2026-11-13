from contextlib import redirect_stdout
import io
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_bringup_transport import cases, check_case, exercise, compile_native, completion_cases, check_completion_case
from test_bringup_transport import submission_cases, check_submission_case
from test_bringup_transport import handoff_cases, check_handoff_case, extract_handoff_filters, check_handoff_pipeline


class TransportRunnerTests(unittest.TestCase):
    def test_handoff_cases_cover_partial_graphics_failure_and_both_adoption_refusals(self):
        self.assertEqual({'ok', 'gfx-timeout', 'gfx-wrong-scratch', 'gfx-wrong-memory',
                          'compute-adopt-status', 'gfx-adopt-status'}, set(handoff_cases()))
        self.assertEqual(6, len(handoff_cases()))

    def test_handoff_accounting_rejects_swallowed_failure_or_wrong_queue_inputs(self):
        gpu = {'scheduler_bells': 4, 'work_bells': 2, 'adoptions': 1, 'writes_after_failure': 0, 'sleeps': 55}
        handoff = {'fake_transport_successes': 1, 'fake_transport_refusals': 0,
                   'graphics_preamble_dwords': 960,
                   'adoption_requests': [[0x2540000, 1024, 0x2541000, 24, 8, 0x2550000]]}
        def result(gpu=gpu, handoff=handoff, code=75, stdout=''):
            return subprocess.CompletedProcess([], code, stdout, 'mesboot GPU: gfx execution not confirmed\n'
                'fake-gpu-summary ' + json.dumps(gpu) + '\nfake-handoff-summary ' + json.dumps(handoff))
        self.assertEqual(handoff, check_handoff_case(result(), 'gfx-wrong-memory')['handoff'])
        for invalid in (result(code=0), result(stdout='gpu-returned'), result(gpu={**gpu, 'adoptions': 2}),
                        result(gpu={**gpu, 'sleeps': 0}), result(gpu={**gpu, 'writes_after_failure': 1}),
                        result(handoff={**handoff, 'fake_transport_successes': True}),
                        result(handoff={**handoff, 'fake_transport_refusals': 1}),
                        result(handoff={**handoff, 'adoption_requests': []})):
            with self.assertRaises(RuntimeError): check_handoff_case(invalid, 'gfx-wrong-memory')

    def test_exact_source_filters_and_fake_claim_hook_are_validated(self):
        full = (ROOT / 'tools/phxctl/full.sh').read_text()
        boot = (ROOT / 'tools/phxctl/phxboot.sh').read_text()
        self.assertEqual(('tail -12', 'grep -E "^compute:|^gfx:|adopt"'), extract_handoff_filters(full, boot))
        for a, b in ((full * 2, boot), (full, boot * 2), (full.replace('tail -12', 'tail -12; exit 0'), boot),
                     (full, boot.replace('grep -E', 'grep -F')), ('', boot)):
            with self.assertRaises(RuntimeError): extract_handoff_filters(a, b)
        text = 'compute: synthetic\nfake-filter-status=0\nfake-claim-requested\n'
        self.assertTrue(check_handoff_pipeline(subprocess.CompletedProcess([], 0, text, ''))['claim_hook_requested'])
        for code, stdout in ((1, text), (0, text.replace('compute:', 'absent:')),
                             (0, text.replace('fake-claim-requested\n', '')), (0, text + 'fake-claim-requested\n')):
            with self.assertRaises(RuntimeError): check_handoff_pipeline(subprocess.CompletedProcess([], code, stdout, ''))

    @unittest.skipIf(os.name == 'nt' or not shutil.which('clang'), 'POSIX Clang required for actual fake-I/O C')
    def test_actual_handoff_and_legacy_filter_compositions(self):
        with tempfile.TemporaryDirectory(prefix='phx-handoff-') as directory, redirect_stdout(io.StringIO()):
            report = exercise(Path(directory) / 'audit')
        self.assertEqual(set(handoff_cases()), {row['case'] for row in report['actual_handoff_cases_passed']})
        self.assertFalse(report['hardware_executed'])
        self.assertFalse(report['driver_runtime_tested'])
        self.assertEqual(52, len(report['fault_injection_cases_passed']))
        self.assertEqual(20, len(report['completion_path_cases_passed']))
        self.assertEqual(16, len(report['submission_boundary_cases_passed']))

    def test_submission_rejection_has_no_transport_or_state_changes(self):
        data = {"calls": 0, "ring_writes": 0, "wptr": 897, "seq": 0}
        def result(summary, status=76):
            return subprocess.CompletedProcess([], status, "", "mesboot submission: rejected\nfake-submission-summary " + json.dumps(summary))
        self.assertEqual(data, check_submission_case(result(data), "ring-one-over"))
        for changed in ({**data, "calls": 1}, {**data, "ring_writes": 1}, {**data, "seq": 1},
                        {**data, "wptr": 0}, {**data, "calls": False}):
            with self.assertRaises(RuntimeError): check_submission_case(result(changed), "ring-one-over")
        for status in (0, -11, 75):
            with self.assertRaises(RuntimeError): check_submission_case(result(data, status), "ring-one-over")

    def test_submission_suite_keeps_positive_boundaries_and_exhaustion(self):
        cases = submission_cases()
        self.assertEqual(16, len(set(cases)))
        for name in ("last-frame", "last-sequence", "unaligned", "ring-high-word", "sequence-exhausted"):
            self.assertIn(name, cases)
        for fault, wptr, seq in (("last-frame", 1024, 1), ("last-sequence", 128, (1 << 64) - 1)):
            data = {"calls": 142, "ring_writes": 128, "wptr": wptr, "seq": seq}
            result = subprocess.CompletedProcess([], 0, "submission-returned", "fake-submission-summary " + json.dumps(data))
            self.assertEqual(data, check_submission_case(result, fault))

    def test_failures_cannot_return_zero_or_continue_writes(self):
        valid = subprocess.CompletedProcess([], 74, "", "fake-transport call=1 selector=2\nmesboot transport: stopping\n")
        check_case(valid, 74, 1)
        for invalid in (subprocess.CompletedProcess([], 0, "", valid.stderr),
                        subprocess.CompletedProcess([], -11, "", valid.stderr),
                        subprocess.CompletedProcess([], 74, "transport-returned", valid.stderr),
                        subprocess.CompletedProcess([], 74, "", valid.stderr + "fake-transport call=2 selector=108\n"),
                        subprocess.CompletedProcess([], 74, "", "fake-transport call=1 selector=2\n")):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                check_case(invalid, 74, 1)

    def test_cases_include_both_length_directions_and_valid_zero_data(self):
        actual = list(cases())
        self.assertEqual(52, len(actual))
        self.assertEqual(len(actual), len({(op, mode) for op, mode, _, _ in actual}))
        for op in ("rd", "vr", "vr64", "wr", "sm", "read-then-write", "vram-read-then-write"):
            self.assertIn((op, "short", 74, 1), actual)
            self.assertIn((op, "long", 74, 1), actual)
            self.assertIn((op, "zero", 0, 2 if "-then-" in op else 1), actual)

    def test_host_rejection_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch("test_bringup_transport.platform.system", return_value="Windows"):
            out = Path(temporary) / "new"
            for function in (exercise, compile_native):
                with self.assertRaises(RuntimeError):
                    function(out)
            self.assertFalse(out.exists())

    def test_completion_cases_cover_each_adoption_prerequisite(self):
        actual = list(completion_cases())
        self.assertEqual(20, len(actual))
        for operation in ("mes", "sched", "compute", "gfx"):
            self.assertIn((operation, "ok"), actual)
            self.assertIn((operation, "timeout"), actual)
        for operation in ("compute", "gfx"):
            self.assertIn((operation, "wrong-scratch"), actual)
            self.assertIn((operation, "wrong-memory"), actual)
        for operation in ("mes", "sched"):
            self.assertIn((operation, "wrong-fence-high"), actual)
            self.assertIn((operation, "wrong-token-high"), actual)

    def test_completion_failure_cannot_adopt_write_continue_or_skip_polling(self):
        data = {"scheduler_bells": 1, "work_bells": 1, "adoptions": 0, "writes_after_failure": 0, "sleeps": 51}
        def result(summary, code=75, stdout="", diagnostic="mesboot GPU: compute execution not confirmed\n"):
            return subprocess.CompletedProcess([], code, stdout, diagnostic + "fake-gpu-summary " + json.dumps(summary))
        self.assertEqual(data, check_completion_case(result(data), "compute", "timeout"))
        for changed in ({**data, "adoptions": 1}, {**data, "writes_after_failure": 1},
                        {**data, "sleeps": 0}, {**data, "work_bells": 0}, {**data, "work_bells": True}):
            with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                check_completion_case(result(changed), "compute", "timeout")
        for invalid in (result(data, code=0), result(data, code=-11), result(data, stdout="gpu-returned"),
                        result(data, diagnostic="")):
            with self.assertRaises(RuntimeError):
                check_completion_case(invalid, "compute", "timeout")


if __name__ == "__main__":
    unittest.main()
