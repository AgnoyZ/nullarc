from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_submit_diagnostic import exercise, extract


class SubmitDiagnosticTests(unittest.TestCase):
    def test_actual_dispatcher_propagates_errors_and_limits_logs_under_sanitizers(self):
        with tempfile.TemporaryDirectory() as directory:
            report = exercise(Path(directory) / 'result')
        self.assertEqual(74, report['cases'])
        self.assertEqual(31, report['non_submit_dispatch_paths'])
        self.assertFalse(report['hardware_executed'])
        self.assertFalse(report['kernel_loaded'])

    def test_missing_or_duplicate_actual_definition_is_rejected(self):
        source = (ROOT / 'src/phxbringup/PhxBringup.cpp').read_text()
        method, state = extract(source)
        for changed in (source + method, source + state,
                        source.replace(state.rstrip('\n'), ''), source.replace(method, '')):
            with self.subTest(size=len(changed)):
                with self.assertRaisesRegex(RuntimeError, 'one actual native dispatcher'):
                    extract(changed)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            marker = out / 'preserve.txt'
            marker.write_text('original')
            with self.assertRaisesRegex(RuntimeError, 'output exists'):
                exercise(out)
            self.assertEqual('original', marker.read_text())


if __name__ == '__main__':
    unittest.main()
