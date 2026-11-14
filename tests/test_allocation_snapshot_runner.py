from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_allocation_snapshot import extract, exercise
from test_snapshot_lifecycle import extract as extract_lifecycle


class AllocationSnapshotTests(unittest.TestCase):
    def test_actual_dispatcher_and_snapshot_under_sanitizers(self):
        with tempfile.TemporaryDirectory() as temp:
            report = exercise(Path(temp) / 'new')
        self.assertEqual(30, report['cases'])
        self.assertEqual(17, report['reader_cases'])
        self.assertEqual(16, report['lifecycle_cases'])
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

    def test_lifecycle_extraction_requires_actual_methods_and_default_state(self):
        source = (ROOT / 'src/phxbringup/PhxBringup.cpp').read_text()
        for marker in ('PhxBringup::newUserClient(', 'PhxBringup::claimSession(',
                       'PhxBringup::releaseSession(', 'IOAccelPhxNativeClient::initWithTask(',
                       'IOAccelPhxNativeClient::start(', 'IOAccelPhxNativeClient::closeResources(',
                       'IOAccelPhxNativeClient::clientClose(', 'IOAccelPhxNativeClient::free(',
                       'IOAccelPhxNativeClient::freeAll(', 'PhxBringup *owner{nullptr};',
                       'uint64_t pendFenceSeq{0};', 'volatile SInt32 sessionOpen{0};'):
            with self.subTest(marker=marker), self.assertRaises(RuntimeError):
                extract_lifecycle(source.replace(marker, 'missing'))
        with self.assertRaises(RuntimeError): extract_lifecycle(source * 2)
        methods = extract_lifecycle(source)['lifecycle-methods.inc']
        self.assertNotIn('PhxBringup::readRegs(', methods)
        self.assertEqual(1, methods.count('PhxBringup::claimSession('))
        self.assertEqual(1, methods.count('PhxBringup::releaseSession('))

    def test_workflow_and_read_only_client_contract(self):
        # Optional diagnostics must not add a dependency to isolated legacy ABI fixtures.
        self.assertNotIn('PhxAllocationSnapshot.h', (ROOT / 'src/phxbringup/PhxNativeABI.h').read_text())
        for name in ('build.yml', 'kernel-compile-check.yml'):
            self.assertIn('python3 tools/test_allocation_snapshot.py', (ROOT / '.github/workflows' / name).read_text())
        source = (ROOT / 'tools/allocation_snapshot.cpp').read_text()
        self.assertEqual(1, source.count('IOConnectCallMethod('))
        self.assertNotIn('PHXN_SEL_HELLO', source)
        self.assertNotIn('PHXN_SEL_QUERYINFO', source)


if __name__ == '__main__': unittest.main()
