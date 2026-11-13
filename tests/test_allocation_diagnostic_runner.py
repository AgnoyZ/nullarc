from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_allocation_diagnostic import BUSY_CASES, HOST_CASES, extract, exercise


class AllocationDiagnosticTests(unittest.TestCase):
    def test_actual_source_and_counter_declarations_fail_closed(self):
        source = (ROOT / 'src/phxbringup/PhxBringup.cpp').read_text(encoding='utf-8')
        fragments = extract(source)
        for text in fragments.values():
            for line in text.splitlines():
                self.assertIn(line, source)
        for marker in ('PhxBringup::queueProgress(', 'PhxBringup::gpuRetiredLocked(',
                       'PhxBringup::vmIdleLocked(', 'PhxBringup::vmMap(', 'PhxBringup::vmUnmap(',
                       'IOAccelPhxNativeClient::doGemVa(', 'IOAccelPhxNativeClient::doBoImportHost(',
                       'uint8_t allocationFailureLogs[3]', 'uint8_t busyLogs[2][2]'):
            # The context structure extraction must retain its diagnostic counters as well.
            if 'busyLogs' in marker:
                self.assertIn(marker, fragments['bo-structures.inc'])
                continue
            with self.assertRaises(RuntimeError):
                extract(source.replace(marker, 'missing'))
        with self.assertRaises(RuntimeError): extract(source * 2)

    def test_cases_are_unique_and_ci_wired(self):
        self.assertEqual(len(BUSY_CASES + HOST_CASES), len(set(BUSY_CASES + HOST_CASES)))
        for cases, filename in ((BUSY_CASES, 'test_allocation_diagnostic.cpp'),
                                (HOST_CASES, 'test_host_import_diagnostic.cpp')):
            text = (ROOT / 'tests' / filename).read_text(encoding='utf-8')
            for case in cases:
                self.assertIn('"' + case + '"', text)
        self.assertIn('python3 tools/test_allocation_diagnostic.py', (ROOT / '.github/workflows/build.yml').read_text())

    def test_unsupported_host_and_existing_output_refuse(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'new'
            with mock.patch('test_allocation_diagnostic.platform.system', return_value='Windows'):
                with self.assertRaises(RuntimeError): exercise(out)
            self.assertFalse(out.exists())
            out.mkdir()
            with self.assertRaises(RuntimeError): exercise(out)


if __name__ == '__main__': unittest.main()
