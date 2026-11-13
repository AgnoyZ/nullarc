from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_allocation_snapshot import extract, exercise


class AllocationSnapshotTests(unittest.TestCase):
    def test_actual_dispatcher_and_snapshot_under_sanitizers(self):
        with tempfile.TemporaryDirectory() as temp:
            report = exercise(Path(temp) / 'new')
        self.assertEqual(30, report['cases'])
        self.assertEqual(17, report['reader_cases'])
        self.assertFalse(report['hardware_executed'])
        self.assertFalse(report['kernel_loaded'])

    def test_missing_and_ambiguous_definitions_fail_closed(self):
        source = (ROOT / 'src/phxbringup/PhxBringup.cpp').read_text(encoding='utf-8')
        for marker in ('IOAccelPhxNativeClient::doAllocationSnapshot(', 'PhxBringup::recordAllocation(',
                       'PhxBringup::copyAllocationSnapshot(', 'PhxAllocationHistory allocationHistory{};',
                       '#define PHX_KEXT_BUILD '):
            with self.subTest(marker=marker), self.assertRaises(RuntimeError):
                extract(source.replace(marker, 'missing'))
        with self.assertRaises(RuntimeError): extract(source * 2)

    def test_existing_output_refuses(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'output exists'): exercise(Path(temp))

    def test_workflow_and_read_only_client_contract(self):
        for name in ('build.yml', 'kernel-compile-check.yml'):
            self.assertIn('python3 tools/test_allocation_snapshot.py', (ROOT / '.github/workflows' / name).read_text())
        source = (ROOT / 'tools/allocation_snapshot.cpp').read_text()
        self.assertEqual(1, source.count('IOConnectCallMethod('))
        self.assertNotIn('PHXN_SEL_HELLO', source)
        self.assertNotIn('PHXN_SEL_QUERYINFO', source)


if __name__ == '__main__': unittest.main()
