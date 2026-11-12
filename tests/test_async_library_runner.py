from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from test_async_library import extract, exercise


class AsyncLibraryRunnerTests(unittest.TestCase):
    def test_actual_bodies_and_existing_pool_extraction_fails_closed(self):
        source = (ROOT / 'src/nmplugin/NVMTLDevice.m').read_text(encoding='utf-8')
        methods, helpers = extract(source)
        self.assertEqual(methods.count('addOperationWithBlock:'), 2)
        self.assertIn('NVMTL_PIPELINE_THREADS', helpers)
        self.assertIn('maxConcurrentOperationCount', helpers)
        for changed in ('', source + source,
                        source.replace('static int nvmtl_sysctl_int(const char *name)', 'static int missing(const char *name)'),
                        source.replace('completionHandler:(MTLNewLibraryCompletionHandler)h', 'missingHandler:(MTLNewLibraryCompletionHandler)h')):
            with self.assertRaises(RuntimeError):
                extract(changed)

    def test_snapshot_and_async_admission_are_required(self):
        source = (ROOT / 'src/nmplugin/NVMTLDevice.m').read_text(encoding='utf-8')
        for changed in (source.replace('[desc copy]', 'desc').replace('[src copy]', 'src').replace('[opt copy]', 'opt'),
                        source.replace('addOperationWithBlock:', 'missingOperation:'),
                        source.replace('dispatch_async(', 'missing_dispatch(')):
            with self.assertRaises(RuntimeError):
                extract(changed)

    def test_non_macos_does_not_claim_native_execution(self):
        for system in ('Windows', 'Linux'):
            with tempfile.TemporaryDirectory() as temp, mock.patch('test_async_library.platform.system', return_value=system):
                out = Path(temp) / 'fresh'
                with self.assertRaises(RuntimeError):
                    exercise(out)
                self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
