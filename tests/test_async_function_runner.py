from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_async_function import extract, exercise


class AsyncFunctionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'src/nmplugin/NVMTLObjects.m').read_text(encoding='utf-8')
        self.device = (ROOT / 'src/nmplugin/NVMTLDevice.m').read_text(encoding='utf-8')

    def test_actual_bodies_share_existing_pool(self):
        methods, helpers = extract(self.source, self.device)
        self.assertEqual(methods.count('addOperationWithBlock:'), 2)
        self.assertIn('functionDescriptor.constantValues copy]', methods)
        self.assertIn('NVMTL_PIPELINE_THREADS', helpers)
        for source, device in (('', self.device), (self.source + self.source, self.device),
                               (self.source, self.device.replace('#import "NVMTLObjects.m"', '')),
                               (self.source, self.device.replace('static int nvmtl_sysctl_int(', 'static int missing('))):
            with self.assertRaises((RuntimeError, ValueError)):
                extract(source, device)

    def test_snapshot_dispatch_and_nil_handler_are_required(self):
        for changed in (self.source.replace('copy]', 'missingCopy]'),
                        self.source.replace('addOperationWithBlock:', 'missingOperation:'),
                        self.source.replace('dispatch_async(', 'missing_dispatch('),
                        self.source.replace('if (!handler) return;', '')):
            with self.assertRaises(RuntimeError):
                extract(changed, self.device)

    def test_non_macos_does_not_claim_native_execution(self):
        for system in ('Windows', 'Linux'):
            with tempfile.TemporaryDirectory() as temp, mock.patch('test_async_function.platform.system', return_value=system):
                out = Path(temp) / 'fresh'
                with self.assertRaises(RuntimeError):
                    exercise(out)
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
